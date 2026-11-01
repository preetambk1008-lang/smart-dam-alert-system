const express = require('express');
const cors = require('cors');
const path = require('path');
const { 
    calculateHaversineDistance, 
    calculateWaveArrival, 
    evaluateReservoirStatus, 
    evaluateFarmerRisk 
} = require('./civilHydrology');
const { INITIAL_DAM_DATA, INITIAL_FARMERS } = require('./seedData');

const app = express();
const PORT = process.env.PORT || 5000;

app.use(cors());
app.use(express.json());

// In-Memory Database (persists during server lifetime, initialized with realistic seed data)
let damState = { ...INITIAL_DAM_DATA };
let farmersList = INITIAL_FARMERS.map(f => {
    const dist = calculateHaversineDistance(
        INITIAL_DAM_DATA.latitude,
        INITIAL_DAM_DATA.longitude,
        f.latitude,
        f.longitude
    );
    return {
        ...f,
        distanceKm: dist
    };
});

let alertDispatchLog = [
    {
        id: "ALERT-INIT-001",
        timestamp: new Date(Date.now() - 3600000).toISOString(),
        farmerId: "FARM-001",
        farmerName: "Ramesh Gowda",
        phone: "+919845012345",
        surveyNumber: "142/2A",
        tier: "CRITICAL",
        channel: "WHATSAPP & SMS",
        message: "🚨 URGENT FLOOD WARNING: KRS Dam outflow 38,000 cusecs. Flood wave reaching Survey No 142/2A in ~15 mins. Evacuate immediately!",
        status: "DELIVERED"
    }
];

// Helper to refresh all farmer risks based on current dam telemetry
function getEnrichedFarmers() {
    const damEvaluation = evaluateReservoirStatus(damState);
    return farmersList.map(f => {
        const dist = calculateHaversineDistance(
            damState.latitude,
            damState.longitude,
            f.latitude,
            f.longitude
        );
        const farmerWithDist = { ...f, distanceKm: dist };
        const risk = evaluateFarmerRisk(farmerWithDist, damEvaluation, damState.outflowCusecs);
        return {
            ...farmerWithDist,
            riskAssessment: risk
        };
    });
}

// ----------------------------------------------------------------------------
// API ROUTES
// ----------------------------------------------------------------------------

// 0. Serve Frontend Web Dashboard
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, '..', 'frontend', 'index.html'));
});

// 1. GET Dam Telemetry & Hydrological Evaluation
app.get('/api/dam', (req, res) => {
    const evaluation = evaluateReservoirStatus(damState);
    res.json({
        dam: damState,
        evaluation
    });
});

// 2. POST Update Dam Water Levels & Controls (from Dam Authority Panel)
app.post('/api/dam/update', (req, res) => {
    const {
        currentTmc,
        waterLevelMeters,
        inflowCusecs,
        outflowCusecs,
        season
    } = req.body;

    if (currentTmc !== undefined) damState.currentTmc = parseFloat(currentTmc);
    if (waterLevelMeters !== undefined) damState.waterLevelMeters = parseFloat(waterLevelMeters);
    if (inflowCusecs !== undefined) damState.inflowCusecs = parseInt(inflowCusecs, 10);
    if (outflowCusecs !== undefined) damState.outflowCusecs = parseInt(outflowCusecs, 10);
    if (season !== undefined) damState.season = season;
    damState.lastUpdated = new Date().toISOString();

    const evaluation = evaluateReservoirStatus(damState);
    res.json({
        message: "Dam hydrological parameters updated successfully",
        dam: damState,
        evaluation
    });
});

// 3. GET All Registered Farmers with Real-time Risk Assessment
app.get('/api/farmers', (req, res) => {
    const enriched = getEnrichedFarmers();
    res.json({
        total: enriched.length,
        farmers: enriched
    });
});

// 4. POST Register New Farmer Land & Survey Number
app.post('/api/farmers/register', (req, res) => {
    const {
        name,
        phone,
        surveyNumber,
        village,
        district,
        cropType,
        landAreaAcres,
        latitude,
        longitude,
        distanceFromRiverMeters,
        notes
    } = req.body;

    if (!name || !phone || !surveyNumber || !latitude || !longitude) {
        return res.status(400).json({ error: "Missing required fields (Name, Phone, Survey No, Latitude, Longitude)" });
    }

    const lat = parseFloat(latitude);
    const lon = parseFloat(longitude);
    const dist = calculateHaversineDistance(damState.latitude, damState.longitude, lat, lon);

    const newFarmer = {
        id: `FARM-${Date.now().toString().slice(-4)}`,
        name,
        phone,
        surveyNumber,
        village: village || "Downstream Sector",
        district: district || damState.district,
        cropType: cropType || "Paddy",
        landAreaAcres: parseFloat(landAreaAcres) || 2.0,
        latitude: lat,
        longitude: lon,
        distanceKm: dist,
        distanceFromRiverMeters: parseInt(distanceFromRiverMeters, 10) || 300,
        notes: notes || "Newly registered farmland"
    };

    farmersList.unshift(newFarmer);

    const evaluation = evaluateReservoirStatus(damState);
    const risk = evaluateFarmerRisk(newFarmer, evaluation, damState.outflowCusecs);

    res.status(201).json({
        message: "Farmland registered successfully",
        farmer: {
            ...newFarmer,
            riskAssessment: risk
        }
    });
});

// 5. POST Broadcast Alerts to Specific Risk Tier or Distance Radius
app.post('/api/alerts/broadcast', (req, res) => {
    const { targetZone, customNote } = req.body; // '0-2km' | '2-5km' | 'all-critical' | 'all'
    const enriched = getEnrichedFarmers();
    const evaluation = evaluateReservoirStatus(damState);

    let recipients = [];
    if (targetZone === '0-2km') {
        recipients = enriched.filter(f => f.distanceKm <= 2.0);
    } else if (targetZone === '2-5km') {
        recipients = enriched.filter(f => f.distanceKm > 2.0 && f.distanceKm <= 5.0);
    } else if (targetZone === 'all-critical') {
        recipients = enriched.filter(f => f.riskAssessment.riskTier === 'CRITICAL');
    } else {
        recipients = enriched;
    }

    const newDispatches = recipients.map(farmer => {
        const wave = farmer.riskAssessment.waveArrival;
        const etaText = wave.arrivalMinutes ? `ETA: ~${wave.arrivalMinutes} mins.` : "Discharge gates closed.";
        
        const messageText = `🌊 *JAL-SURAKSHA FLOOD ALERT* - ${damState.name}\n` +
            `Hello *${farmer.name}*,\n` +
            `📍 *Survey No*: ${farmer.surveyNumber} (${farmer.village})\n` +
            `⚠️ *Dam Status*: ${evaluation.alertTitle}\n` +
            `💧 *Storage*: ${damState.currentTmc} TMC (${evaluation.fillPercentage}%)\n` +
            `🚪 *Outflow*: ${damState.outflowCusecs.toLocaleString()} cusecs\n` +
            `⏱️ *Flood Wave Arrival*: ${etaText}\n` +
            `🚨 *Advisory*: ${farmer.riskAssessment.actionRecommendation}\n` +
            (customNote ? `📝 *Notice*: ${customNote}\n` : '') +
            `Please move cattle and machinery to high ground!`;

        const dispatchItem = {
            id: `ALERT-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
            timestamp: new Date().toISOString(),
            farmerId: farmer.id,
            farmerName: farmer.name,
            phone: farmer.phone,
            surveyNumber: farmer.surveyNumber,
            tier: farmer.riskAssessment.riskTier,
            channel: "WHATSAPP & SMS",
            message: messageText,
            status: "DELIVERED",
            // Direct WhatsApp web link for click-to-send demonstration
            whatsappUrl: `https://api.whatsapp.com/send?phone=${farmer.phone.replace(/[^0-9]/g, '')}&text=${encodeURIComponent(messageText)}`
        };

        return dispatchItem;
    });

    alertDispatchLog = [...newDispatches, ...alertDispatchLog].slice(0, 100);

    res.json({
        message: `Alert broadcast sent successfully to ${newDispatches.length} farmers`,
        count: newDispatches.length,
        targetZone,
        dispatches: newDispatches
    });
});

// 6. GET Alert Dispatch History
app.get('/api/alerts/history', (req, res) => {
    res.json({
        total: alertDispatchLog.length,
        logs: alertDispatchLog
    });
});

// 7. GET System Health & Civil Engineering Constants
app.get('/api/system-info', (req, res) => {
    res.json({
        system: "JalSuraksha Civil Hydrological Monitoring & Flood Alert System",
        version: "2.0.0",
        department: "Department of Civil Engineering",
        curriculum: "5th Semester Capstone Project",
        standards: "Central Water Commission (CWC) Rule Curve Guidelines & IS 7323",
        hydraulicFormulas: {
            floodWaveSpeed: "Dynamic celerity v = 7.5 to 14.0 km/h based on spillway discharge Q",
            geofencing: "Haversine Great-Circle Distance + Riverbed Proximity Buffering",
            ruleCurve: "Monsoon cushion vs Winter Rabi conservation vs Summer drinking pool"
        }
    });
});

app.listen(PORT, () => {
    console.log(`=======================================================`);
    console.log(`🌊 JALSURAKSHA CIVIL DAM ALERT SERVER RUNNING`);
    console.log(`📡 Port: http://localhost:${PORT}`);
    console.log(`📊 Civil Hydrology Rule Curve & GIS Geofencing Active`);
    console.log(`=======================================================`);
});
