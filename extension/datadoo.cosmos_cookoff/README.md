# Datadoo Cosmos Cookoff IsaacSim Extension

## Install into development environment
- IsaacSim (used 6.0.0-dev for this extension)
- Clone this project in your environment `<env_path>/<repository_path>`
```
git clone https://github.com/datadoo/cosmos_cookoff.git
```
- Add `<env_path>/<repository_path>/extension` to IsaacSim extensions:
  - Open you .kit file you use for your development:
    `<isaacsim_path>/apps/isaacsim.exp.full.kit`
  - Add the following lines:
    - Under `[dependencies]`:
    ```
    [dependencies]
    "datadoo.cosmos_cookoff" = {}
    ```
    - After `[settings]` block:
    ```
    app.exts.devFolders.'++' = [ 
    <env_path>/<repository_path>/extension,
    ]
    ```
