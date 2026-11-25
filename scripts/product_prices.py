"""Hand-checked typical retail prices for every product readers can see.

Why this file exists: the old backfill guessed prices from a per-poll category
tier (e.g. every product in the sleep poll was priced like a mattress, so a
$35 sleep mask showed $759). These are typical US (amazon.com) and German
(amazon.de) shelf prices, rounded, checked by hand in Nov 2026. They are NOT
live Amazon prices (there is no PA-API account).

Used by scripts/backfill_prices_and_merchants.py: a product whose title matches
a row here always gets that price (re-running the backfill re-applies them), so
a "Regenerate" in the admin can't bring guessed numbers back for these products.
Products with no row fall back to the category estimate in that script.

Each row: (title regex, USD, EUR). Matching is case-insensitive, `re.search`
on the product title, FIRST MATCH WINS — so put specific rows above generic
ones (e.g. "audible.*jahresabo" above "audible"). A price is either a number
(formatted per locale: "$1,299" / "1.299 €") or a string used verbatim (for
subscriptions like "$14.95/mo"). None = no price known for that locale; the
backfill then falls back to its category estimate.

Add a row whenever a new product shows up (the backfill prints unmatched
titles). Keep prices to whole units except subscriptions.
"""

PRODUCT_PRICES = [
    # --- Running watches -------------------------------------------------
    (r"forerunner 265",                       349, 349),
    (r"forerunner 965",                       499, 499),
    (r"forerunner 55\b",                      199, 179),
    (r"garmin venu 3",                        449, 399),
    (r"coros pace 3",                         229, 229),
    (r"polar pacer pro",                      299, 279),

    # --- Luggage ---------------------------------------------------------
    (r"away the large carry-on",              295, None),
    (r"away the carry-on",                    275, None),
    (r"travelpro platinum elite",             389, None),
    (r"samsonite outline pro",                249, None),
    (r"samsonite winfield 3",                 199, None),
    (r"monos carry-on pro",                   295, None),
    (r"rimowa original cabin",                None, 1350),
    (r"rimowa essential cabin",               None, 750),
    (r"samsonite c-lite",                     None, 319),
    (r"tumi alpha 3",                         None, 795),
    (r"samsonite proxis",                     None, 329),
    (r"horizn studios m5",                    None, 395),
    (r"osprey farpoint 40",                   185, 169),

    # --- Sunscreen -------------------------------------------------------
    (r"eltamd uv clear",                      43, None),
    (r"eltamd uv sport",                      30, None),
    (r"supergoop!? unseen",                   38, None),
    (r"supergoop!? play",                     22, None),
    (r"anthelios melt-in milk",               37, None),
    (r"neutrogena ultra sheer",               11, None),
    (r"anthelios uv ?mist",                   None, 21),
    (r"anthelios (uvmune|invisible)",         None, 22),
    (r"isdin eryfotona",                      None, 35),
    (r"isdin (fotoprotector )?fusion water",  None, 26),
    (r"altruist",                             None, 13),
    (r"eucerin sun",                          None, 18),
    (r"altapharma",                           None, 5),

    # --- Grills ----------------------------------------------------------
    (r"weber performer deluxe",               549, 749),
    (r"weber original kettle premium",        219, None),
    (r"kamado joe classic iii",               1799, None),
    (r"kamado joe classic ii\b",              1199, 1399),
    (r"pk grills pk300",                      499, None),
    (r"big green egg large",                  None, 1395),
    (r"big green egg medium",                 None, 1049),
    (r"monolith classic pro",                 None, 1799),
    (r"napoleon rodeo",                       None, 349),
    (r"landmann.*grill chef",                 None, 49),

    # --- Home gym / workout ----------------------------------------------
    (r"bowflex select ?tech 552",             399, 429),
    (r"fitness reality 810xlt",               249, None),
    (r"concept2 rowerg",                      990, None),
    (r"trx go",                               119, None),
    (r"trx all-in-one",                       169, 179),
    (r"rep fitness flat utility bench",       159, None),
    (r"rep fitness ab-3000",                  379, None),
    (r"letsfit resistance bands",             25, None),
    (r"sunny health & fitness rowing",        249, None),
    (r"lululemon the exercise mat",           108, None),
    (r"kettlebell kings powder coat",         89, None),
    (r"kettlebell kings cast iron",           79, None),
    (r"fit simplify",                         12, 12),
    (r"resistance bands set \(heavy duty",    29, None),
    (r"runner's guide to strength training",  20, None),
    (r"lifeline klimmzugstange",              None, 39),
    (r"major fitness.*trainingsmatte",        None, 39),
    (r"lifeline power wheel",                 None, 59),
    (r"rollga foam roller",                   None, 49),
    (r"rubber gym.*gymnastikmatte",           None, 49),
    (r"bodylastics",                          None, 45),
    (r"amazon basics kurzhanteln",            None, 29),
    (r"trainingsbuch",                        None, 24),
    (r"kettlebell gusseisen",                 None, 49),
    (r"fitnessbänder set",                    None, 15),
    (r"home-gym starter-kit",                 None, 149),
    (r"kettlebell-set mit trainingsplan",     None, 59),
    (r"klarfit meteor",                       None, 39),

    # --- Video doorbells -------------------------------------------------
    (r"ring video doorbell pro 2",            229, 229),
    (r"nest doorbell",                        179, None),
    (r"arlo essential video doorbell wire-free", 149, None),
    (r"arlo video doorbell \(avd1001\)",      129, None),
    (r"arlo (essential )?video doorbell (2|2k)", None, 149),
    (r"blink video doorbell",                 69, None),
    (r"reolink video türklingel",             None, 89),

    # --- Coffee ----------------------------------------------------------
    (r"breville barista express",             699, 599),
    (r"breville bambino plus",                499, None),
    (r"stilosa",                              99, None),
    (r"nespresso vertuo pop",                 99, None),
    (r"dedica arte",                          299, 249),
    (r"dedica style",                         None, 159),
    (r"la specialista maestro",               1199, None),
    (r"la specialista prestigio",             None, 599),
    (r"dinamica",                             899, None),
    (r"barista touch impress",                None, 1249),
    (r"barista touch",                        None, 949),
    (r"jura e8",                              None, 1099),
    (r"philips 3200.*lattego",                None, 449),

    # --- TVs -------------------------------------------------------------
    (r"qn65q80c",                             999, None),
    (r"samsung 55\" 4k qled tv \(q80c\)",     799, None),
    (r"xr-65x90l",                            1099, None),
    (r"sony x90l 65",                         None, 1099),
    (r"65ur8000",                             499, None),
    (r"a80l",                                 1299, None),
    (r"tcl 55\" 4k qled tv \(q6",             349, None),
    (r"85\" qn90d",                           2999, None),
    (r"lg 77\" c4 oled",                      2499, None),
    (r"hisense 100\" u8n",                    2999, None),
    (r"qn85b 75",                             1599, None),
    (r"lg c3 77",                             2299, None),
    (r"tcl qm8 75",                           1299, None),
    (r"oled65c4|oled evo c4 65",              None, 1599),
    (r"gu65cu8079",                           None, 549),
    (r"xr-65xr70",                            None, 1299),
    (r"gu43cu8079",                           None, 329),
    (r"50qned756",                            None, 449),
    (r"kd-55x85l",                            None, 849),
    (r"qn85c 65",                             None, 1199),
    (r"qn95c 75",                             None, 2499),
    (r"lg oled evo g4 77",                    None, 3499),
    (r"hisense u8n 75",                       None, 1199),

    # --- Sunglasses ------------------------------------------------------
    (r"ray-ban rb3025|aviator classic",       None, 159),
    (r"ray-ban (wayfarer classic|rb2132|new wayfarer|wayfarer rb2132)", 171, 149),
    (r"goodr og",                             35, None),
    (r"maui jim punchbowl",                   299, None),
    (r"knockaround",                          35, None),
    (r"privé revaux",                         40, None),
    (r"rheos sapelos",                        74, None),
    (r"oakley holbrook",                      None, 139),
    (r"polaroid pld",                         None, 39),
    (r"carrera 1021",                         None, 119),

    # --- Sleep -----------------------------------------------------------
    (r"hatch restore 2",                      169, None),
    (r"tempur-adapt.*(mattress|hybrid)",      2599, None),
    (r"tempur-adapt cooling pillow",          199, None),
    (r"tempur-adapt pillow",                  179, None),
    (r"withings sleep tracking mat",          129, None),
    (r"oura ring gen3",                       299, None),
    (r"bose sleepbuds ii",                    249, None),
    (r"manta sleep mas(k|ke) pro",            79, 79),
    (r"manta sleep mask",                     35, None),
    (r"philips smartsleep wake-up light",     None, 99),
    (r"philips smartsleep.*stirnband",        None, 299),
    (r"tempur-cloud kissen",                  None, 119),
    (r"tempur-comfort kopfkissen",            None, 99),
    (r"beurer sl 10",                         None, 39),
    (r"vivosmart 5",                          None, 129),

    # --- Running shoes ---------------------------------------------------
    (r"brooks ghost 16",                      140, 150),
    (r"gel-nimbus 26",                        160, 179),
    (r"gel-kayano 31",                        165, 179),
    (r"fresh foam x 880 ?v14",                140, 149),
    (r"fresh foam x 1080v13",                 165, 169),
    (r"nike invincible 3",                    180, None),
    (r"nike pegasus 41",                      None, 139),
    (r"nike revolution 7",                    None, 59),
    (r"runfalcon 3",                          None, 49),
    (r"gel-contend 8",                        None, 65),

    # --- Reading ---------------------------------------------------------
    (r"audible.*jahresabo",                   None, 99),
    (r"audible.*3 monate",                    None, "29,85 €"),
    (r"audible",                              "$14.95/mo", "9,95 €/Monat"),
    (r"kindle paperwhite",                    159, 169),
    (r"kindle scribe",                        449, 469),
    (r"tolino shine 6",                       None, 129),
    (r"tolino shine 5",                       None, 119),

    # --- Vacuums ---------------------------------------------------------
    (r"roomba j7\+",                          599, 549),
    (r"roborock s8 pro ultra",                1299, 999),
    (r"roborock q5 pro\+",                    None, 399),
    (r"robovac x9 pro",                       599, 599),
    (r"robovac x8 pro",                       449, 449),
    (r"robovac x8 hybrid",                    349, 329),

    # --- Mattresses ------------------------------------------------------
    (r"saatva classic",                       2099, None),
    (r"nectar premier",                       1199, None),
    (r"tuft & needle original",               795, None),
    (r"casper original foam",                 1195, None),
    (r"zinus green tea",                      299, None),
    (r"emma one",                             None, 449),
    (r"casper (sleep )?original matratze",    None, 899),
    (r"casper essential",                     None, 499),
    (r"dormeo octaspring",                    None, 599),
    (r"dormeo options hybrid",                None, 399),
    (r"tempur original matratze",             None, 2399),

    # --- Kitchen knives --------------------------------------------------
    (r"victorinox fibrox",                    49, 39),
    (r"wüsthof classic",                      170, 119),
    (r"shun classic",                         175, 169),
    (r"mac knife professional",               175, None),
    (r"kitcheniq",                            10, None),
    (r"wmf spitzenklasse",                    None, 59),

    # --- Air purifiers ---------------------------------------------------
    (r"levoit core 300s",                     149, 149),
    (r"coway ap-1512hh",                      229, None),
    (r"coway airmega 400s",                   549, None),
    (r"coway airmega 200m",                   229, None),
    (r"dyson purifier cool formaldehyde",     649, 549),
    (r"dyson purifier cool tp07",             549, 449),
    (r"philips series 800",                   None, 99),
    (r"blueair blue pure 411i",               None, 199),

    # --- Office / back ---------------------------------------------------
    (r"herman miller aeron",                  1895, 1699),
    (r"steelcase leap",                       1399, 1299),
    (r"secretlab titan evo",                  549, 549),
    (r"flexispot e7",                         599, 549),
    (r"autonomous ergochair pro",             499, None),
    (r"capisco 8106",                         None, 899),
    (r"ergotopia nextback",                   None, 499),
    (r"ergotron lx",                          None, 349),
    (r"topo anti-fatigue",                    None, 119),

    # --- Sustainable sneakers --------------------------------------------
    (r"veja v-10 vegan",                      165, 155),
    (r"veja v-10",                            175, 165),
    (r"danner mountain light",                440, None),
    (r"birkenstock boston",                   160, None),
    (r"birkenstock arizona",                  None, 119),
    (r"stan smith mylo",                      100, 109),
    (r"allbirds (tree|wool) runner",          98, 109),
    (r"nat-2 mushroom",                       249, None),
    (r"nat-2 multicolor",                     None, 149),
    (r"nat-2 fusion",                         None, 159),
    (r"merrell bare access",                  130, None),
    (r"arkk copenhagen",                      None, 139),
    (r"vaude moab",                           None, 139),
    (r"novesta star master",                  None, 79),

    # --- Pet food --------------------------------------------------------
    (r"royal canin breed health",             79, 69),
    (r"royal canin size health",              69, 75),
    (r"hill's science (diet|plan)",           75, 75),
    (r"orijen original",                      115, 109),
    (r"stella & chewy's",                     35, None),
    (r"primal pet foods",                     39, None),
    (r"instinct raw boost",                   25, None),
    (r"the farmer's dog",                     "$129/mo", None),
    (r"nom nom",                              "$119/mo", None),
    (r"smalls fresh cat",                     "$69/mo", None),
    (r"pets deli",                            None, 29),
    (r"tackenberg",                           None, 39),
    (r"kiezekopp",                            None, 49),
    (r"primal roots barf",                    None, 39),
    (r"mush b\.a\.r\.f",                      None, 45),
    (r"wolf of wilderness",                   None, 35),
    (r"josera minette",                       None, 35),

    # --- Skincare --------------------------------------------------------
    (r"truskin vitamin c",                    25, None),
    (r"paula's choice 10% niacinamide",       49, None),
    (r"paula's choice.*2% bha|paula's choice skin perfecting", 35, 35),
    (r"paula's choice skin balancing",        None, 27),
    (r"roc retinol correxion",                29, None),
    (r"olay regenerist",                      29, None),
    (r"neutrogena rapid wrinkle",             25, None),
    (r"cerave foaming facial",                17, None),
    (r"cerave schäumendes",                   None, 13),
    (r"effaclar mat",                         37, 19),
    (r"effaclar duo",                         30, 19),
    (r"differin",                             15, None),
    (r"cosrx bha",                            None, 19),
    (r"nivea cellular expert",                None, 19),
    (r"revitalift laser",                     None, 17),
    (r"eucerin hyaluron-filler",              None, 32),
    (r"mela b3",                              None, 45),
    (r"anew vitamin c",                       None, 19),
    (r"eucerin anti-pigment",                 None, 39),

    # --- Bikes and bike gear ---------------------------------------------
    (r"cannondale treadwell 3",               775, None),
    (r"cannondale treadwell 2",               949, None),
    (r"cannondale topstone 4",                1099, 1199),
    (r"co-op cycles adv 2\.2",                1599, None),
    (r"ride1up 500",                          1195, None),
    (r"ride1up prodigy",                      1995, None),
    (r"topeak prepstation",                   999, None),
    (r"lezyne super gps",                     139, None),
    (r"trek fx sport 4",                      1999, None),
    (r"trek fx 3",                            None, 1099),
    (r"schwinn discover",                     449, None),
    (r"radcity 5 plus",                       1699, None),
    (r"cube cross hybrid pro 500 allroad",    None, 2599),
    (r"cube cross hybrid pro 500",            None, 2499),
    (r"cube cross race c:62",                 None, 2299),
    (r"cube touring hybrid pro 625",          None, 2899),

    # --- Headphones ------------------------------------------------------
    (r"sony wh-1000xm5",                      329, 299),
    (r"bose quietcomfort ultra",              379, 379),
    (r"airpods max",                          499, 529),
    (r"jabra evolve2 55",                     None, 229),
    (r"jabra evolve2 85",                     None, 329),

    # --- Thermostats -----------------------------------------------------
    (r"nest learning thermostat \(3",         None, 219),
    (r"nest learning thermostat",             279, 279),
    (r"ecobee premium",                       249, None),
    (r"honeywell home t9",                    169, None),
    (r"amazon smart thermostat",              79, None),
    (r"tado",                                 None, 149),
    (r"bosch smart home raumthermostat",      None, 79),
    (r"bosch easycontrol",                    None, 179),
]

# No comparison ("Best Buy" / "Otto") price for these: those shops don't sell
# subscriptions or books, so a made-up comparison price would look fake.
NO_ALT_PRICE = [
    r"audible",
    r"the farmer's dog",
    r"nom nom",
    r"smalls fresh cat",
    r"runner's guide to strength training",
    r"trainingsbuch",
]
