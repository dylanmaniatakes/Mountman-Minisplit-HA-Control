# Releasing Test Versions for HACS

HACS can install from the default branch, but testing is easier when GitHub releases are used. A release lets Home Assistant users choose or roll back to a known version.

## Version Bump Checklist

1. Update the integration version:

```json
{
  "version": "0.1.1"
}
```

File:

```text
custom_components/mountman_minisplit/manifest.json
```

2. Commit the changes.

3. Create and push a matching git tag:

```bash
git tag v0.1.1
git push origin main
git push origin v0.1.1
```

4. Create a GitHub release from that tag.

5. In Home Assistant, open HACS and redownload/update `Mountman Mini-Split IR`.

## Version Naming

Use small test releases while the protocol is still being proven:

```text
v0.1.0
v0.1.1
v0.1.2
```

When the core cool/heat/off behavior has been proven on hardware, move toward:

```text
v1.0.0
```

## What Should Trigger a New Test Release

- A packet field changes.
- A new temperature or mode is added.
- A Home Assistant service schema changes.
- A climate entity behavior changes.
- A bug fix affects what gets transmitted.
