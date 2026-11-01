/**
 * REFERENCE DAM & DOWNSTREAM AGRICULTURAL LAND REGISTRY
 * 
 * Benchmark Dam: Krishnarajasagara (KRS) Dam / Cauvery River Basin
 * Location: Lat 12.2707° N, Lon 76.5742° E
 * Full Reservoir Level (FRL): 124.80 m (409.45 ft)
 * Maximum Water Level (MWL): 125.50 m (411.75 ft)
 * Gross Storage Capacity: 49.45 TMC
 * Dead Storage: 4.38 TMC
 * Spillway Gates: 136 radial & sluice gates
 */

const INITIAL_DAM_DATA = {
    id: "DAM-KRS-001",
    name: "Krishnarajasagara (KRS) Dam",
    river: "Cauvery River",
    district: "Mandya / Mysuru",
    state: "Karnataka",
    latitude: 12.2707,
    longitude: 76.5742,
    fullReservoirLevelMeters: 124.80,
    maxWaterLevelMeters: 125.50,
    deadStorageTmc: 4.38,
    maxCapacityTmc: 49.45,
    
    // Live Dynamic State (controllable via Dashboard)
    currentTmc: 46.80,              // High storage during peak monsoon
    waterLevelMeters: 123.90,       // Near FRL
    inflowCusecs: 48000,            // Heavy catchment rain
    outflowCusecs: 38000,           // Spillway discharge
    season: "monsoon",              // 'monsoon' | 'winter' | 'summer'
    lastUpdated: new Date().toISOString()
};

// Realistic downstream farmers registered with land survey numbers, crops & locations
const INITIAL_FARMERS = [
    {
        id: "FARM-001",
        name: "Ramesh Gowda",
        phone: "+919845012345",
        email: "ramesh.gowda.farmer@gmail.com",
        surveyNumber: "142/2A",
        village: "Belagola",
        district: "Mandya",
        cropType: "Paddy (Rice)",
        landAreaAcres: 3.5,
        latitude: 12.2685,
        longitude: 76.5880,
        distanceFromRiverMeters: 180, // Very close to river bed
        notes: "Electric pump installed near river bank"
    },
    {
        id: "FARM-002",
        name: "Suresh Patel",
        phone: "+919880198765",
        email: "suresh.patel.farms@gmail.com",
        surveyNumber: "88/1B",
        village: "Belagola Downstream",
        district: "Mandya",
        cropType: "Sugarcane",
        landAreaAcres: 5.0,
        latitude: 12.2650,
        longitude: 76.5820,
        distanceFromRiverMeters: 220,
        notes: "Has 8 dairy cows and tractor shed"
    },
    {
        id: "FARM-003",
        name: "Manjula Devi",
        phone: "+919741234567",
        email: "manjula.devi.agri@gmail.com",
        surveyNumber: "204/3",
        village: "Hosa Belagola",
        district: "Mandya",
        cropType: "Banana & Turmeric",
        landAreaAcres: 2.8,
        latitude: 12.2610,
        longitude: 76.5910,
        distanceFromRiverMeters: 310,
        notes: "Drip irrigation infrastructure"
    },
    {
        id: "FARM-004",
        name: "Basavaraj Shivappa",
        phone: "+919448123789",
        email: "basavaraj.mandya@gmail.com",
        surveyNumber: "95/4C",
        village: "Palahalli East",
        district: "Mandya",
        cropType: "Sugarcane",
        landAreaAcres: 6.2,
        latitude: 12.2840,
        longitude: 76.6020,
        distanceFromRiverMeters: 450,
        notes: "Storage godown with harvested jaggery"
    },
    {
        id: "FARM-005",
        name: "Anand Kumar",
        phone: "+919900234112",
        email: "anand.vegetables@gmail.com",
        surveyNumber: "311/1",
        village: "Palahalli Ghat",
        district: "Mandya",
        cropType: "Vegetables (Tomato/Chilli)",
        landAreaAcres: 1.8,
        latitude: 12.2890,
        longitude: 76.6110,
        distanceFromRiverMeters: 120, // Critical low-lying plot
        notes: "Flash flood prone terrain"
    },
    {
        id: "FARM-006",
        name: "Devendrappa K.",
        phone: "+919844556677",
        email: "devendrappa.srirangapatna@gmail.com",
        surveyNumber: "73/2",
        village: "Srirangapatna Island West",
        district: "Mandya",
        cropType: "Paddy",
        landAreaAcres: 4.1,
        latitude: 12.3120,
        longitude: 76.6820,
        distanceFromRiverMeters: 380,
        notes: "Historic island flood corridor"
    },
    {
        id: "FARM-007",
        name: "Shivanna Gowda",
        phone: "+919731998811",
        email: "shivanna.gowda11@gmail.com",
        surveyNumber: "119/5A",
        village: "Mahadevapura",
        district: "Mandya",
        cropType: "Sugarcane & Ragi",
        landAreaAcres: 7.5,
        latitude: 12.3350,
        longitude: 76.7150,
        distanceFromRiverMeters: 650,
        notes: "Adjacent to canal feeder channel"
    },
    {
        id: "FARM-008",
        name: "Lakshmamma",
        phone: "+919611223344",
        email: "lakshmamma.ganjam@gmail.com",
        surveyNumber: "56/1",
        village: "Ganjam Riverbank",
        district: "Mandya",
        cropType: "Betel Leaf & Coconut",
        landAreaAcres: 2.2,
        latitude: 12.3480,
        longitude: 76.7320,
        distanceFromRiverMeters: 150,
        notes: "River confluence point"
    },
    {
        id: "FARM-009",
        name: "Chetan Prasad",
        phone: "+919988776655",
        email: "chetan.prasad.agri@gmail.com",
        surveyNumber: "28/4",
        village: "Hongalli Canal Zone",
        district: "Mandya",
        cropType: "Maize & Pulses",
        landAreaAcres: 5.5,
        latitude: 12.3650,
        longitude: 76.7600,
        distanceFromRiverMeters: 900,
        notes: "Upland farm, safe from 2-meter rise"
    },
    {
        id: "FARM-010",
        name: "Naveen Raj",
        phone: "+919123456789",
        email: "naveen.floriculture@gmail.com",
        surveyNumber: "180/7",
        village: "Arakere",
        district: "Mandya",
        cropType: "Floriculture (Marigold/Jasmine)",
        landAreaAcres: 3.0,
        latitude: 12.3800,
        longitude: 76.7900,
        distanceFromRiverMeters: 1100,
        notes: "Canal command area"
    }
];

module.exports = {
    INITIAL_DAM_DATA,
    INITIAL_FARMERS
};
