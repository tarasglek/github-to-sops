# Changelog

## 3.1.1

* Fixed `import-keys --inplace-edit` so imported SSH recipients are inserted into an existing SOPS `age` key group instead of being appended at the YAML document root.  #26

## 3.1.0

* Changed `github-to-sops install` to install the newest supported SOPS `v3.x` release instead of a hardcoded exact SOPS version.
