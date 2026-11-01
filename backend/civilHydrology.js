/**
 * CIVIL ENGINEERING HYDROLOGY & HYDRAULIC COMPUTATION ENGINE
 * Designed for: Smart Dam Water Level Monitoring & Downstream Flood Early Warning System
 * Department of Civil Engineering - 5th Semester Capstone Project
 * 
 * Standards & References:
 * - Central Water Commission (CWC) Guidelines for Reservoir Operation & Rule Curves
 * - IS 7323: Code of practice for operation of reservoirs
 * - Hydraulic Flood Wave Celerity (Manning's Equation & Saint-Venant shallow wave approximation)
 */

// Haversine formula: Computes great-circle distance between two GPS coordinates in Kilometers
function calculateHaversineDistance(lat1, lon1, lat2, lon2) {
    const R = 6371; // Earth's mean radius in km
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = 
        Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * 
        Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return parseFloat((R * c).toFixed(2)); // Distance in km
}

/**
 * Flood Wave Routing & Travel Time Estimation
 * Standard hydraulic wave celerity: c = sqrt(g * y_m) + v_0
 * For natural alluvial river beds with bed slope S_0 ≈ 0.0005 to 0.001:
 * Empirical flood wave speed ranges between 2.2 m/s (8 km/h) to 3.5 m/s (12.6 km/h)
 * depending on spillway discharge (Q in cusecs).
 */
function calculateWaveArrival(distanceKm, dischargeCusecs) {
    // If no water discharge, flood wave is not propagating downstream
    if (dischargeCusecs <= 500) {
        return {
            arrivalMinutes: null,
            speedKmh: 0,
            statusText: "Spillway gates closed / Base flow only"
        };
    }

    // Dynamic wave velocity based on discharge volume
    // High discharge (e.g. 80,000 cusecs) propagates faster down channel
    let speedKmh = 7.5; // Base flood wave speed (~2.1 m/s)
    if (dischargeCusecs > 20000) speedKmh = 9.0;
    if (dischargeCusecs > 50000) speedKmh = 11.5;
    if (dischargeCusecs > 80000) speedKmh = 14.0;

    const arrivalHours = distanceKm / speedKmh;
    const arrivalMinutes = Math.round(arrivalHours * 60);

    let statusText = "";
    if (arrivalMinutes < 30) {
        statusText = `CRITICAL: Reaching survey plot in ${arrivalMinutes} mins! Evacuate immediately.`;
    } else if (arrivalMinutes < 60) {
        statusText = `HIGH ALERT: Reaching plot in ${arrivalMinutes} mins. Move livestock & pumps.`;
    } else {
        const hrs = (arrivalMinutes / 60).toFixed(1);
        statusText = `ADVISORY: Reaching plot in approx ${hrs} hours.`;
    }

    return {
        arrivalMinutes,
        speedKmh,
        statusText
    };
}

/**
 * Reservoir Rule Curve & Seasonal Risk Evaluation
 * Central Water Commission (CWC) Multi-Tier Thresholds:
 * - Monsoon: High runoff risk, strict safety cushion needed.
 * - Winter: Storage conservation for Rabi crops, higher threshold permitted.
 * - Summer: Low storage, focus on canal irrigation scheduling.
 */
function evaluateReservoirStatus(dam) {
    const {
        currentTmc,
        maxCapacityTmc,
        waterLevelMeters,
        fullReservoirLevelMeters,
        inflowCusecs,
        outflowCusecs,
        season // 'monsoon' | 'winter' | 'summer'
    } = dam;

    const fillPercentage = parseFloat(((currentTmc / maxCapacityTmc) * 100).toFixed(1));

    let alertLevel = "GREEN"; // 'GREEN' | 'YELLOW' | 'ORANGE' | 'RED'
    let alertTitle = "Normal Condition";
    let summaryMessage = "Reservoir levels are well within safe operating limits.";
    let gateStatus = "Normal Flow / Spillway Gates Closed";

    // Seasonal thresholds
    if (season === "monsoon") {
        if (fillPercentage >= 95 || (fillPercentage >= 88 && inflowCusecs > 50000) || outflowCusecs >= 50000) {
            alertLevel = "RED";
            alertTitle = "EMERGENCY: RED FLOOD ALERT";
            summaryMessage = `Monsoon flood crest reached! Reservoir at ${fillPercentage}% capacity. Outflow discharge is ${outflowCusecs.toLocaleString()} cusecs. Immediate evacuation required for downstream floodplain.`;
            gateStatus = "Spillway Crest Gates Fully Opened";
        } else if (fillPercentage >= 85 || inflowCusecs > 35000 || outflowCusecs >= 25000) {
            alertLevel = "ORANGE";
            alertTitle = "HIGH ALERT: ORANGE WARNING";
            summaryMessage = `Reservoir storage at ${fillPercentage}%. High catchment inflows (${inflowCusecs.toLocaleString()} cusecs). Spillway discharge initiated (${outflowCusecs.toLocaleString()} cusecs).`;
            gateStatus = "Spillway Radial Gates Partially Opened";
        } else if (fillPercentage >= 75 || inflowCusecs > 20000) {
            alertLevel = "YELLOW";
            alertTitle = "ADVISORY: YELLOW ALERT";
            summaryMessage = `Reservoir at ${fillPercentage}%. Inflows increasing due to catchment rainfall. Pre-cautionary downstream alert activated.`;
            gateStatus = "Canal Sluices Active / Spillway Standby";
        } else {
            alertLevel = "GREEN";
            alertTitle = "NORMAL: GREEN SAFE";
            summaryMessage = `Reservoir at ${fillPercentage}%. Inflows stable. Normal monsoon retention curve maintained.`;
            gateStatus = "Spillway Closed / River Base Flow Only";
        }
    } else if (season === "winter") {
        // Winter (Rabi season): Target is storage retention up to 95-98%
        if (fillPercentage >= 98 || outflowCusecs >= 40000) {
            alertLevel = "RED";
            alertTitle = "EMERGENCY: RED LEVEL REACHED";
            summaryMessage = `Winter maximum storage exceeded (${fillPercentage}%). Controlled spillway release in progress.`;
            gateStatus = "Spillway Relief Gates Active";
        } else if (fillPercentage >= 92 || outflowCusecs >= 20000) {
            alertLevel = "ORANGE";
            alertTitle = "CAUTION: HIGH WINTER STORAGE";
            summaryMessage = `Reservoir filled to ${fillPercentage}% for Rabi irrigation. Downstream low-lying zones alerted for canal surges.`;
            gateStatus = "Irrigation Canals at Full Supply Depth";
        } else if (fillPercentage >= 80) {
            alertLevel = "YELLOW";
            alertTitle = "WINTER MONITORING: YELLOW";
            summaryMessage = `Healthy reservoir volume (${fillPercentage}%). Water reserved for agricultural feeding.`;
            gateStatus = "Canal Supply Active";
        } else {
            alertLevel = "GREEN";
            alertTitle = "OPTIMAL: WINTER CONSERVATION";
            summaryMessage = `Storage at ${fillPercentage}%. Stable Rabi irrigation supply.`;
            gateStatus = "Controlled Discharge";
        }
    } else { // Summer (Hot Season)
        // In summer, reservoir is depleted for drinking and pre-monsoon inspection
        if (outflowCusecs > 15000) {
            alertLevel = "ORANGE";
            alertTitle = "CANAL SURGE ALERT: SUMMER";
            summaryMessage = `Sudden heavy release into irrigation canals. Farmers near canals advised to take caution.`;
            gateStatus = "Emergency Canal Flushing";
        } else if (fillPercentage < 20) {
            alertLevel = "YELLOW";
            alertTitle = "DROUGHT ADVISORY: LOW STORAGE";
            summaryMessage = `Reservoir at ${fillPercentage}% (Conservation / Dead storage pool). Water strictly rationed for drinking and essential crops.`;
            gateStatus = "Drinking Water Sluice Only";
        } else {
            alertLevel = "GREEN";
            alertTitle = "NORMAL: SUMMER STAGE";
            summaryMessage = `Reservoir at ${fillPercentage}%. Rotational canal irrigation schedule active.`;
            gateStatus = "Rotational Canal Release";
        }
    }

    return {
        fillPercentage,
        alertLevel,
        alertTitle,
        summaryMessage,
        gateStatus,
        waterHead: (waterLevelMeters - (fullReservoirLevelMeters - 20)).toFixed(2)
    };
}

/**
 * Computes individual farmer risk tier based on:
 * 1. Dam alert state
 * 2. Radial distance from dam
 * 3. Distance from river bank (floodplain corridor)
 * 4. Flood wave arrival time
 */
function evaluateFarmerRisk(farmer, damStatus, outflowCusecs) {
    const { distanceKm, distanceFromRiverMeters } = farmer;
    const wave = calculateWaveArrival(distanceKm, outflowCusecs);

    let riskTier = "SAFE"; // 'CRITICAL' | 'WARNING' | 'ADVISORY' | 'SAFE'
    let badgeColor = "green";
    let actionRecommendation = "Conditions normal. Regular farming activities can continue.";

    if (damStatus.alertLevel === "RED") {
        if (distanceKm <= 2.0 || distanceFromRiverMeters <= 250) {
            riskTier = "CRITICAL";
            badgeColor = "red";
            actionRecommendation = "🚨 MANDATORY EVACUATION: Immediate flash flood hazard! Unchain livestock, turn off electrical pumps, and proceed to designated high-ground relief centers immediately!";
        } else if (distanceKm <= 5.0 || distanceFromRiverMeters <= 600) {
            riskTier = "WARNING";
            badgeColor = "orange";
            actionRecommendation = "⚠️ PREPARE TO EVACUATE: Move cattle, pump motors, and farm machinery to elevated ground. Keep emergency kit and battery torches ready.";
        } else {
            riskTier = "ADVISORY";
            badgeColor = "yellow";
            actionRecommendation = "📢 FLOOD ADVISORY: Riverbank submerged downstream. Stay away from canal banks and river crossings.";
        }
    } else if (damStatus.alertLevel === "ORANGE") {
        if (distanceKm <= 2.0) {
            riskTier = "WARNING";
            badgeColor = "orange";
            actionRecommendation = "⚠️ HIGH CAUTION: Spillway release initiated. Do not venture into riverbed or low-lying survey plots.";
        } else if (distanceKm <= 5.0) {
            riskTier = "ADVISORY";
            badgeColor = "yellow";
            actionRecommendation = "📢 ADVISORY: River channel rising. Secure irrigation pipes and temporary bunds.";
        } else {
            riskTier = "SAFE";
            badgeColor = "green";
            actionRecommendation = "Normal vigilance. Follow local village panchayat announcements.";
        }
    } else if (damStatus.alertLevel === "YELLOW") {
        if (distanceKm <= 2.0) {
            riskTier = "ADVISORY";
            badgeColor = "yellow";
            actionRecommendation = "📢 EARLY NOTICE: Catchment receiving heavy rainfall. Dam gates may open in the next 12-24 hours.";
        } else {
            riskTier = "SAFE";
            badgeColor = "green";
            actionRecommendation = "Safe. Regular agricultural operations.";
        }
    } else {
        riskTier = "SAFE";
        badgeColor = "green";
        actionRecommendation = "Green Safe Zone. Normal irrigation schedule active.";
    }

    return {
        riskTier,
        badgeColor,
        actionRecommendation,
        waveArrival: wave
    };
}

module.exports = {
    calculateHaversineDistance,
    calculateWaveArrival,
    evaluateReservoirStatus,
    evaluateFarmerRisk
};
