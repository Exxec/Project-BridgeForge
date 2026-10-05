# Mod changelog

Bigger updates to revived mods, newest first. Tool changes are in CHANGELOG.md; each mod's evidence is in its revival report.

## 2026-10-04

- **Seeker [BF r4]** 0.3.0-0.98a+bf.4: Organic hull: heal, shed, hammer and projectile timers and the field radius are now kept per ship (they were shared by every ship with the hull mod, so one ship's timing drove the others). Patched into SEEKER.jar from a Vineflower decompile; reopened after it was wrongly closed as superseded by 0.6.6, a different mod (5 of 37 ships shared).
- **Doc's Needless Economic Expansion Pack** 0.2.0 Mann Co+bf.1: Guarded setIndustryOnPlanet/setConditionOnPlanet against a missing star system: a save without Corvus/Samarra/Galatia/Aztlan (Nexerelin random sector) crashed on load with a NullPointerException (owner crash log 2026-10-04).
- **RogueSynth [BF r1]** 0.0.1-beta.4+bf.2: revived for RC8 and archived (ready for live test)
- **Legacy of Arkgneisis [BF r2]** v2.0a DEV+bf.3: revived for RC8 and archived (ready for live test)
- **Megastructures Tab** 1.0.0+bf.1: revived for RC8 and archived (ready for live test)
- ** Slightly Better Tech-Mining** 0.95.1-2.6.0+bf.1: revived for RC8 and archived (ready for live test)
- **Doc's Needless Economic Expansion Pack** 0.2.0 Mann Co+bf.1: revived for RC8 and archived (ready for live test)
- **Zorg18** V18+bf.5: Zorg Zeta fixed: the modpack port's corona -10000 and radius-0 Zeta I (0.6 arguments shifted) restored to the author's values; system moved to (70000, -40000). Not live-tested.
- **Zorg18** V18+bf.6: Unimatrix is a size 10 colony (was 3), population_10; new campaigns only. Not live-tested.
- **(INCOMPATIBLE WITH STARLORODS) Exigency** 0.8.01a+bf.1: Exipirated Avesta black market: blackMarketMinFuel/Supplies/Marines are read with defaults (50/50/30, the 0.8.1a vanilla values); RC8 has none of these settings and opening the market crashed with JSONException (owner crash log 2026-10-04, via Starpocalypse).
- **(INCOMPATIBLE WITH STARLORODS) Exigency** 0.8.01a+bf.1: revived for RC8 and archived (ready for live test)
- **(INCOMPATIBLE WITH STARLORODS) Exigency** 0.8.01a+bf.2: Exigency and Exipirated ships and Exigency weapons can be bought and raided: the factions knew them by blueprint tags (exigency_bp, exipirated_bp) that no hull or weapon carried (owner report 2026-10-04).
- **(INCOMPATIBLE WITH STARLORODS) Exigency** 0.8.01a+bf.2: revived for RC8 and archived (ready for live test)
- **(INCOMPATIBLE WITH STARLORODS) Exigency** 0.8.01a+bf.3: Avesta Station roams the RC8 core worlds again: its 29 hyperspace waypoints were 0.7-era coordinates (it wandered empty space north-east of the core); each is remapped from the 0.7.2 starmap.json onto RC8's by the three nearest core systems (owner report 2026-10-04).
- **(INCOMPATIBLE WITH STARLORODS) Exigency** 0.8.01a+bf.3: revived for RC8 and archived (ready for live test)
- **(INCOMPATIBLE WITH STARLORODS) Exigency** 0.8.01a+bf.4: Avesta Station shows its name on the map (was icon-only), owner request.
- **(INCOMPATIBLE WITH STARLORODS) Exigency** 0.8.01a+bf.4: revived for RC8 and archived (ready for live test)
- **(INCOMPATIBLE WITH STARLORODS) Exigency** 0.8.01a+bf.5: The Tasserus Ship Graveyard is revealed on the map (vanilla wreck icon and name; it had no icon and was hidden), owner request.
- **(INCOMPATIBLE WITH STARLORODS) Exigency** 0.8.01a+bf.5: revived for RC8 and archived (ready for live test)
- **(INCOMPATIBLE WITH STARLORODS) Exigency** 0.8.01a+bf.6: Factions learn their tagged blueprints on game load, so saves started before bf.2 spawn Exigency fleets
- **(INCOMPATIBLE WITH STARLORODS) Exigency** 0.8.01a+bf.6: revived for RC8 and archived (ready for live test)
- **Adjusted Sector** 0.7.1+bf.1: Ships settings_my.json as settings.json so the sector generator is active (the archive had presets only)
- **Adjusted Sector** 0.7.1+bf.1: revived for RC8 and archived (ready for live test)
- **Omega-Trauma [BF r1]** 0.1.1+bf.2: IIRT_Nor knows the iirt_all_bp hulls (its own tag matched none) and iirt_sd_10 weapons carry iirt_sd_bp, so IIRT_Army knows them
- **Omega-Trauma [BF r1]** 0.1.1+bf.2: revived for RC8 and archived (ready for live test)
- **Fuel Siphoning** 1.2.2+bf.1: Drops the author's 'Change Log.url' web shortcut from the shipped copy
- **Fuel Siphoning** 1.2.2+bf.1: revived for RC8 and archived (ready for live test)
- **Faction Relationships Uniquified** 0.1.1+bf.1: Data/ renamed data/ (case-sensitive systems never found rules.csv; the zip held both spellings)
- **Faction Relationships Uniquified** 0.1.1+bf.1: revived for RC8 and archived (ready for live test)

## 2026-10-03

- **Batavia**: Light Armour, Heavy Armour and Ammo Crates: maneuverability penalties now apply as described (were near-zero bonuses); spawn point survives a sector without Askonia

## 2026-10-02

- **Polaris Prime**: officer picker closes through RC8's dialog callback instead of a simulated Escape keypress (java.awt.Robot)
- **Tore Up Plenty**: Scrap Armour's maneuverability penalty now applies (it was a near-zero bonus from a percent/multiplier mix-up); the description's 'a quarter' is what it does
- **Mountain and Sea**: declares GraphicsLib, which its plugin calls; loose scripts compile under RC8

## 2026-10-01

- **Epta Consortium**: recompiled classes whose game calls changed return type in RC8 (NoSuchMethodError as shipped)
- **Scy Nation**: recompiled classes whose game calls changed return type in RC8 (NoSuchMethodError as shipped)
- **Magellan Shenanigans**: recompiled classes whose game calls changed return type in RC8 (NoSuchMethodError as shipped)
- **Wotani Federation**: ported an on-hit effect to RC8's onHit signature (AbstractMethodError as shipped) and relinked arc calls
- **Polaris Prime**: ported a dialog to RC8's createCustomDialog(panel, callback) (AbstractMethodError as shipped) and relinked a tooltip call
- **Unofficial New Game Plus**: ported two dialogs to RC8's createCustomDialog(panel, callback), added the new buttonPressed callback, relinked 14 tooltip classes
- **VoidTec [BF r1]**: recompiled a tooltip class onto RC8's addCustom(UIComponentAPI, float) overload (NoSuchMethodError as shipped)
- **Kadur Remnant**: missions use RC8's renamed pickPortraitPreferNonDuplicate (NoSuchMethodError as shipped)
- **Dassault-Mikoyan Engineering**: jar classes ported to RC8 interface changes (AbstractMethodError as shipped)
- **Grytpype and Moriarty's Defense Authority**: jar classes ported to RC8 interface changes (AbstractMethodError as shipped)
- **RogueliteSector**: jar classes ported to RC8 interface changes (AbstractMethodError as shipped)
- **ICE**: jar classes ported to RC8 interface changes (AbstractMethodError as shipped)
- **FSF Miltary Company - [a111164_ExtendPack]**: jar classes ported to RC8 interface changes (AbstractMethodError as shipped)
- **Wotani Federation**: jar classes ported to RC8 interface changes (AbstractMethodError as shipped)
- **Polaris Prime**: jar classes ported to RC8 interface changes (AbstractMethodError as shipped)
- **Arkships**: gate picker ported to RC8's CampaignEntityPickerListener (AbstractMethodError as shipped)
- **Roguelite Sector**: startup dialog's anonymous classes ported to RC8 interface changes (AbstractMethodError as shipped)
- **RevenantLib** 1.3.0+bf.1: DroneLib (tomatopaste) folded in whole; its ShipAPI wrapper given the 83 methods RC8 added (AbstractMethodError as shipped)
- **Neutrino Corporation: Nostalgia Edition**: two ship systems ported to RC8's ShipSystemStatsScript (AbstractMethodError as shipped)
- **The Nomads**: a ship system ported to RC8's ShipSystemStatsScript (AbstractMethodError as shipped)
- **(KIND STRANGER) Tiandong Heavy Industries**: fleet inflater given RC8's three new inflater methods, with vanilla's own bodies (AbstractMethodError as shipped)
- **Valkyrians**: relinked a hull-mod class whose game calls changed in RC8 (decompile's lost parentheses restored)
- **Explorer Society [BF r3]**: jar's stale on-hit class replaced by the already-ported script (AbstractMethodError as shipped)
- **Tyrador Safeguard Coalition**: jar's stale on-hit class rebuilt from its already-ported source (AbstractMethodError as shipped)
- **Vanidad y Afliction Operation**: custom collision shape given RC8's two new BoundsAPI methods (AbstractMethodError as shipped)
- **Tore Up Plenty**: 0.8 markets ported: industry-conditions become RC8 industries, addMarket gains RC8's argument, removed smuggling-stability call dropped
- **Tyrador Safeguard Coalition**: forgeship officer creation rebuilt from the author's own newer source (old createOfficer form gone in RC8); tooltip calls relinked
- **Bounties Expanded**: recompiled a skirmish-bounty class whose game calls changed return type in RC8 (NoSuchMethodError as shipped)
- **Special Hullmod Upgrades**: 35 classes relinked and four hull mods ported to RC8's HullModEffect (NoSuchMethodError/AbstractMethodError as shipped)
- **Xenoargh Rebal**: tow cable hull mod ported to RC8's HullModEffect (AbstractMethodError as shipped)

## 2026-09-30

- **Legacy of Arkgneisis** v2.0a DEV+bf.3: relinked a tooltip call RC8 changed (addImageWithText, NoSuchMethodError as shipped); back to live test
- **Megastructures Tab** 1.0.0+bf.1: relinked a tooltip call RC8 changed (addImageWithText); back to live test
- **RogueSynth** 0.0.1-beta.4+bf.2: relinked a hull-mod tooltip call RC8 changed (addImageWithText); back to live test
- **Slightly Better Tech Mining** 0.95.1-2.6.0+bf.1: relinked two industry tooltip calls RC8 changed (addImageWithText); back to live test
- **Too Much Information**: relinked five hull-mod tooltip tables (beginTable, NoSuchMethodError as shipped)
- **Nightcross**: Plasma Aggregator kept one ship's weapon state for every ship; now per ship
- **Better Colonies**: recompiled classes whose game calls changed return type in RC8 (NoSuchMethodError as shipped)
- **Cryosleeper 2 - Domain Electric Boogaloo Edition**: recompiled classes whose game calls changed return type in RC8 (NoSuchMethodError as shipped)
- **Dassault-Mikoyan Engineering dev**: recompiled classes whose game calls changed return type in RC8 (NoSuchMethodError as shipped)
- **Erexeus Technology Complex**: recompiled classes whose game calls changed return type in RC8 (NoSuchMethodError as shipped)
- **Fleet Action History**: recompiled classes whose game calls changed return type in RC8 (NoSuchMethodError as shipped)
- **Holy Covenant of Kemet**: recompiled classes whose game calls changed return type in RC8 (NoSuchMethodError as shipped)
- **ICE**: recompiled classes whose game calls changed return type in RC8 (NoSuchMethodError as shipped)
- **(KIND STRANGER) Foundation Of Borken**: recompiled classes whose game calls changed return type in RC8 (NoSuchMethodError as shipped)
- **Kingdom of Terra**: recompiled classes whose game calls changed return type in RC8 (NoSuchMethodError as shipped)
- **Maelstrom Shadow-Light Power Company**: recompiled classes whose game calls changed return type in RC8 (NoSuchMethodError as shipped)
- **Maelstrom Tahlan Shipworks**: recompiled classes whose game calls changed return type in RC8 (NoSuchMethodError as shipped)
- **Magellan Protectorate**: recompiled classes whose game calls changed return type in RC8 (NoSuchMethodError as shipped)
- **Nomadic Survival**: recompiled classes whose game calls changed return type in RC8 (NoSuchMethodError as shipped)
- **~Ship Catalogue / Variant Editor**: recompiled classes whose game calls changed return type in RC8 (NoSuchMethodError as shipped)
- **Sylphon RnD**: recompiled classes whose game calls changed return type in RC8 (NoSuchMethodError as shipped)
- **Terraformers**: recompiled classes whose game calls changed return type in RC8 (NoSuchMethodError as shipped)
- **[Traverser Design Bureau]**: recompiled classes whose game calls changed return type in RC8 (NoSuchMethodError as shipped)
- **Yuri Expedition**: recompiled classes whose game calls changed return type in RC8 (NoSuchMethodError as shipped)
- **prv Starworks**: recompiled classes whose game calls changed return type in RC8 (NoSuchMethodError as shipped)

## 2026-09-29

- **Broken Star [BF r2] 0.1+bf.2**: revived for RC8 and archived (live validated)
- **Seeker - Unidentified Contact 0.6.6**: revived for RC8 and archived (live validated)
- **FlowerGod**: Chinese text translated in place to English (one mod, not a side-by-side translation)

## 2026-09-28

- **Adjusted Sector 0.7.1**: revived for RC8 and archived (live validated)
- **Amogus Shipyards 1.1.1**: revived for RC8 and archived (live validated)
- **! Angry Periphery 4 1.5**: revived for RC8 and archived (live validated)
- **Arthr's Faction Blender 1.0**: revived for RC8 and archived (live validated)
- **Arthr's Pirates but EPIC 1.0**: revived for RC8 and archived (live validated)
- **Doc's Needless Economic Expansion Pack 0.2.0 Mann Co**: revived for RC8 and archived (live validated)
- **(INCOMPATIBLE WITH STARLORODS) Exigency 0.8.01a**: revived for RC8 and archived (live validated)
- **Logistics Notifications 1.4.4**: revived for RC8 and archived (live validated)
- **M3s Varren Clans test [BF r1] 0.0.1a+bf.1**: revived for RC8 and archived (live validated)
- **Maelstrom Extra Planetary Conditions 1.0.0**: revived for RC8 and archived (live validated)
- **Maelstrom Superweapons Arsenal Older Version 1.7**: revived for RC8 and archived (live validated)
- **Marine Portraits 1.0**: revived for RC8 and archived (live validated)
- **Megastructures Tab 1.0.0**: revived for RC8 and archived (live validated)
- **Meme portraits 1.01**: revived for RC8 and archived (live validated)
- **Missing Names Mod 0.7**: revived for RC8 and archived (live validated)
- **MnemonicSensors 0.2.3**: revived for RC8 and archived (live validated)
- **Omega-Trauma [BF r1] 0.1.1+bf.1**: revived for RC8 and archived (live validated)
- **Piotrs Placeholder 1.0.0**: revived for RC8 and archived (live validated)
- **RemnantPad 1.1**: revived for RC8 and archived (live validated)
- **RogueSynth [BF r1] 0.0.1-beta.4+bf.1**: revived for RC8 and archived (live validated)
- **S-TechPad 1.0**: revived for RC8 and archived (live validated)
- **Union Rail-Systems 0.1**: revived for RC8 and archived (live validated)
- **WalHullmods 0.1**: revived for RC8 and archived (live validated)
- **Starsector AI Overhaul 0.91a+bf.1**: revived for RC8 and archived (live validated)
- **$$ Starsector FX CORE $$ 9.1a+bf.1**: revived for RC8 and archived (live validated)
- **Yunru's Cissonius 0.95.1-1.1**: revived for RC8 and archived (live validated)

## 2026-09-27

- **Accelerated Construction 1.0**: revived for RC8 and archived (live validated)
- **Anex Weapons 0.2.4**: revived for RC8 and archived (live validated)
- **Animal Portrait Pack 0.1**: revived for RC8 and archived (live validated)
- **Legacy of Arkgneisis [BF r2] v2.0a DEV+bf.2**: revived for RC8 and archived (live validated)
- **Aryas Nightingale Ships 0.02**: revived for RC8 and archived (live validated)
- **Baird Jobs 1.0**: revived for RC8 and archived (live validated)
- **Battletech Portrait Pack 1.1**: revived for RC8 and archived (live validated)
- **BF Legacy Fleets 1.0.0**: revived for RC8 and archived (live validated)
- **Blockade Ship 0.11**: revived for RC8 and archived (live validated)
- **Blue Friend Balls 1.0.0**: revived for RC8 and archived (live validated)
- **Boneyard 1.2**: revived for RC8 and archived (live validated)
- **Capture Officers and Crew 1.0.4**: revived for RC8 and archived (live validated)
- **Combat Radar 3.0**: revived for RC8 and archived (live validated)
- **D-MOD Services 0.1.1**: revived for RC8 and archived (live validated)
- **$$$ Dakkaholics Sprites 1.4**: revived for RC8 and archived (live validated)
- **Degenerate Portrait Pack 1.1**: revived for RC8 and archived (live validated)
- **Deluxe Player Flags 1.01a**: revived for RC8 and archived (live validated)
- **Faction Relationships Uniquified 0.1.1**: revived for RC8 and archived (live validated)
- **Filter Hullmods versions are for suckers**: revived for RC8 and archived (live validated)
- **Fuel Siphoning 1.2.2**: revived for RC8 and archived (live validated)
- **Furry Portrait Pack v1.6**: revived for RC8 and archived (live validated)
- **Guardian Prototype 1.1**: revived for RC8 and archived (live validated)
- **Horny Jail 1.0.0**: revived for RC8 and archived (live validated)
- **Interesting Portraits Pack 1.2**: revived for RC8 and archived (live validated)
- **Internal Affairs 1.1**: revived for RC8 and archived (live validated)
- **Invisible Hand, colony markets 1.55**: revived for RC8 and archived (live validated)
- **Jackundor's Advanced Arms 0.4.0**: revived for RC8 and archived (live validated)
- **jeffships 1**: revived for RC8 and archived (live validated)
- **(KIND STRANGER) Automatic Orders 0.3.2**: revived for RC8 and archived (live validated)
- **Less generic relationship descriptions 1.0**: revived for RC8 and archived (live validated)
- **Portrait Faction Expanded: Hegemony 1.00**: revived for RC8 and archived (live validated)
- **Power Fantasy Portrait 1**: revived for RC8 and archived (live validated)
- **Punishing: Gray Raven Portrait Pack 1.1.0**: revived for RC8 and archived (live validated)
- **Reduce Hypershunt Demands 1.0.a**: revived for RC8 and archived (live validated)
- **Remnant Command Transfer 1.0.1**: revived for RC8 and archived (live validated)
- **Ship Browser 0.1.0**: revived for RC8 and archived (live validated)
- **Ship Direction Marker 1.3.1**: revived for RC8 and archived (live validated)
- **Simulator Overhaul 1.4**: revived for RC8 and archived (live validated)
- **Slightly Better Tech-Mining 0.95.1-2.6.0**: revived for RC8 and archived (live validated)
- **SOTF Addon - SPARKLE 6.9**: revived for RC8 and archived (live validated)
- **stinger sector tips tupac fan club**: revived for RC8 and archived (live validated)
- **Subtle Planetary Shield v1.0**: revived for RC8 and archived (live validated)
- **Thumper Madness 0.8a**: revived for RC8 and archived (live validated)
- **Transfer All Items 1.2**: revived for RC8 and archived (live validated)
- **Unconventional Armaments 1.4b**: revived for RC8 and archived (live validated)
- **Yunru's Unpack Blueprints 2.1**: revived for RC8 and archived (live validated)
- **Zorg [BF r4] V18+bf.4**: revived for RC8 and archived (live validated)
