- `gene describe <mod> faction:<id>` closes a faction gene (94.G2 slice 10): the `.faction` file, its `factions.csv` row
  (keyed by the table's `faction` column, as RC7 reads it) and the logo, crest and portrait files are members; every hull,
  weapon, wing and hull mod its lists name is a gene need, a vanilla need or a missing id; code passing the id to
  `getFaction` is a registration. A core faction id is refused, and `gene prove` refuses factions until their proof slice.
  RC8_BEHAVIOUR RC8-46: an unknown variant in `default_ship_roles.json` is Fatal at load.
