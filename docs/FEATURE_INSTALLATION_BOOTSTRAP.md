# Feature Packaging & Installation Bootstrap (Stage 13.8.1)

## Purpose

This stage establishes a safe local development path for packaging, trusting, installing,
registering, and enabling feature modules. It does not bypass manifest validation, dependency
checks, authorization, or Ed25519 package-signature verification.

## Source and installed package locations

- Editable source modules remain under the repository `features/` directory.
- Installed packages are stored under the operating-system application data directory at
  `features/installed/<feature_id>`.
- Temporary package extraction remains under the application data `features/packages/` area.
- The source tree is never used as the installed package destination.

This separation is required because the source checkout already contains
`features/tax_invoice/`; installing to that same path would collide with the editable source.

## Local development publisher setup

Run these commands from the repository root. Store keys outside the repository, for example
in `%LOCALAPPDATA%\\OCR Automation\\publisher-keys`:

```powershell
uv run python tools/create_dev_publisher_key.py "$env:LOCALAPPDATA\\OCR Automation\\publisher-keys"
```

Keep `ocr_automation_dev_ed25519.pem` private and backed up securely. Do not commit it or
send it to anyone. The companion `ocr_automation_dev_public_key.txt` contains only the public
key and can be pasted into Feature Management.

Build the signed Tax Invoice package:

```powershell
uv run python tools/build_feature_package.py tax_invoice `
  --publisher-id ocr_automation_dev `
  --private-key "$env:LOCALAPPDATA\\OCR Automation\\publisher-keys\\ocr_automation_dev_ed25519.pem" `
  --output "$env:LOCALAPPDATA\\OCR Automation\\packages\\tax_invoice-1.0.0.zip"
```

The builder copies the feature source into a temporary staging directory, injects the
`publisher_id`, signs the deterministic package digest, and creates a ZIP. The private key
is not included in the package.

## Trust and install through the application

1. Start the application and sign in as an Administrator.
2. Open **Feature Management**.
3. Select **Trust publisher**.
4. Use publisher ID `ocr_automation_dev`, display name `OCR Automation`, and paste the
   Base64 public key from `ocr_automation_dev_public_key.txt`.
5. Select **Install feature package** and choose the signed ZIP.
6. After successful registration, select **Enable** on the registered Tax Invoice row.
7. Return to Dashboard; **Pembacaan Faktur Pajak** should appear in the feature catalog.

Publisher registration and installation are audited application-service operations and are
protected by `publisher.manage` and `feature.install`. Enabling uses
`feature.configure.<feature_id>`. The application does not auto-trust local packages.

## Important security notes

- Feature packages execute in-process with application privileges; signature verification is
  integrity/authenticity validation, not a sandbox.
- Trust only public keys obtained through a trusted channel.
- Keep private signing keys outside the repository and restrict filesystem access.
- Do not use the development key for production releases. Production should use a separately
  managed publisher identity and key-rotation/revocation procedure.
- Do not edit the Feature Registry database directly. Use Feature Management operations.

## Manual verification checklist

- [ ] The generated ZIP contains one feature root with `manifest.json` and
      `publisher_signature.json`.
- [ ] Publisher trust registration succeeds for an Administrator.
- [ ] Package installation validates signature, manifest, compatibility, and dependencies.
- [ ] Registry shows Tax Invoice in `registered` state after installation.
- [ ] Enabling succeeds and changes state to `enabled`.
- [ ] Dashboard lists the Tax Invoice workspace.
- [ ] The workspace opens and can select a local PDF.
- [ ] An untrusted or modified package is rejected.
