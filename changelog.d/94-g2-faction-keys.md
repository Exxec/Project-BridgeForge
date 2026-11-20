- A faction gene now reads every key of its `.faction` file that names content:
  - **Variants and wings:** `shipRoles`, which RC7 looks up at load (RC8_BEHAVIOUR RC8-46); an id ending in `_wing` is a
    wing. Also `variantOverrides`.
  - **Hulls:** `hullFrequency` and `shipSellFrequency`.
  - **Commodities:** `illegalCommodities`, as `commodity:` needs.

  Any other key that is not plain display data (`music`, `voices`, `names`, `custom`, `factionDoctrine`) becomes a suspect
  at its JSON pointer, as does a read key in an unexpected shape, so nothing it may name is dropped.
