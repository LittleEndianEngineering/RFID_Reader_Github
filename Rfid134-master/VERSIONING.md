# Version control and customer deliveries

## Current tracks

| Track | Identity | Status |
|---|---|---|
| Firmware on customer PCB v2/v3 | 1.5, `main_2Ant`, `dbf098dbd869d88fe63274aad421fdba6d7ed18a` | Customer-delivered baseline |
| Customer dashboard | 6.2.1, built from `4f1f01e22cb9411a7b76aa0c45fdf358053cc1a1` | Packaged; physical/customer acceptance pending |
| Customer release tree | `customer/final-deliverable-rfid-reader-2026`, `0f6ea3f93c688f446b8462d2d49f5758fea09410` | Contains unchanged delivered firmware and dashboard packages |
| Local firmware + original dashboard + mobile | Dirty working tree based on `c17d36c188ca3f82e28b5284dc7ca61641cfb6da` | Experimental; compatibility testing required |

The local firmware still carries the same 1.5 header as delivered firmware, but its
bytes differ. The original local dashboard also retains a historical version header.
Mobile currently declares `1.0.0+1` in `pubspec.yaml`; it has no customer release.
None of these labels establishes compatibility. Use commits and hashes until new
development versions are deliberately assigned.

The customer dashboard's editable source is
`dashboard/customer/src/rfid_dashboard_configure_lightsleep_multibutton_S3_live_2Ant.py`.
`dashboard/src/` is the experimental dashboard, not the customer release source.
The local firmware changes support future BLE/mobile work and still need testing
against both dashboards. Do not flash them onto delivered boards as a dashboard update.

## Independent versions and delivery IDs

Keep this repository together and version each component independently. Use patch
versions for compatible fixes (for example dashboard 6.2.2), minor versions for
compatible features, and major versions for breaking changes. Introduce explicit
prerelease labels for new experimental work, such as firmware `1.6.0-dev.1`, when
that work is committed; this guide does not change existing source headers.

A delivery ID identifies the complete combination sent to a customer:

| Delivery | Firmware | Dashboard | Mobile |
|---|---|---|---|
| v6, prepared now | 1.5 / `dbf098d` | 6.2.1 | Excluded |
| v6.1, example dashboard correction | Unchanged | 6.2.2 | Excluded |
| Future mobile pilot | Explicit tested firmware commit | Explicit tested dashboard version | Explicit pilot version/build |

Never overwrite an already sent ZIP, executable, source snapshot, release tag or
release record. Rebuilding the same source can change executable bytes; record
new hashes and use a new delivery ID if a customer receives the rebuilt package.
The v6 record pins the simplified customer ZIP, not the earlier detailed draft.

## Branches, commits and tags

For customer fixes, create a short branch from the customer release commit/tag.
For firmware/mobile experiments, use a separate development branch and working
directory. The current working copy contains uncommitted experiments: do not run
`git add .`, switch it over to the customer branch, reset it or stash it as an
automatic setup step. Commit its work deliberately on its development track.

The Git root is the parent `Code` directory. To create an isolated customer-fix
checkout from the current project directory:

```sh
git worktree add -b fix/dashboard-reconnect ../rfid-customer-v6.1 0f6ea3f93c688f446b8462d2d49f5758fea09410
```

That example starts at the existing release commit; also bring the reviewed
versioning records/tools into the new branch once those are committed. This setup
does not change the current branch, commit dirty experiments, or create worktrees.

Use annotated tags, with immutable targets:

| Tag | Target commit |
|---|---|
| `firmware/v1.5` | `dbf098dbd869d88fe63274aad421fdba6d7ed18a` |
| `dashboard/v6.2.1` | `4f1f01e22cb9411a7b76aa0c45fdf358053cc1a1` |
| `delivery/v6` | `0f6ea3f93c688f446b8462d2d49f5758fea09410` |

These are proposed tags recorded in `release_records/delivery-v6.json`; they are
not created or pushed by this setup. The delivery tag identifies the component/
artifact release tree. The separately versioned delivery record identifies the
exact customer ZIP, README and reference source by hash. Future records belong in
their release commit before its delivery tag is created.

A branch/tag is a complete repository snapshot, so the customer branch includes
baseline firmware source. Its changes are dashboard/build changes; firmware stays
identical to the delivered baseline. Publish only reviewed paths/commits and explicit
tags. Do not force-move a tag when feedback arrives. The existing remote default
`main` is older and must not be used as the current release baseline.

## Release records and checks

Developer-only records live in `release_records/`; customer packages stay simple:
applications, the long-named reference `.py`, and a short README.

- `delivery-v6.json`: exact firmware, dashboard source/build, platform hashes,
  customer ZIP hash and acceptance state. This is the frozen v6 identity.
- `development-2026-11-17.json`: hashes identifying the local experimental firmware,
  original dashboard and selected mobile sources. It is an observation, not a
  backup, release or compatibility certification. The uncommitted files must still
  be preserved/committed independently.
- `feedback-template.md`: customer issue and acceptance evidence template.

From this project directory, use Python 3.9+ (standard library only):

```sh
python3 tools/check_delivery.py
# Also verify the exact simple customer ZIP, if it is present locally:
python3 tools/check_delivery.py --package 'dashboard/deliverables/deliverable v6/rfid_deliverable_v6.zip'
# Check a proposed committed customer update against this frozen delivery:
python3 tools/check_delivery.py --candidate <commit>
# Detect accidental use of local experimental firmware/source for this delivery:
python3 tools/check_delivery.py --working-tree
```

The default check reads committed Git objects, so dirty experimental files cannot
masquerade as released firmware. `--working-tree` is expected to FAIL in the current
mixed development checkout. It compares the firmware, customer source and packaging
with their pinned commits. The original experimental dashboard/mobile paths are
outside the customer build. A failure here does not modify or discard any files.

The check also verifies the canonical platform packages and exact release source
snapshot; those must be present locally (download Git LFS objects first). It is an
identity check, not a hardware compatibility test. A future intentional component
update needs its own new record; it should not pass as the unchanged v6 release.

## Handling customer feedback

1. Record delivery ID, OS/processor, dashboard/firmware versions, PCB revision,
   reproduction steps and results using `feedback-template.md`. Mark acceptance
   separately from the immutable release record; do not assume a prepared package
   has already been sent or accepted.
2. Branch from the released customer commit. For a dashboard-only fix, preserve
   firmware `dbf098d`, change only the customer dashboard/build paths, and bump its
   version consistently (protocol constants, source header and packaging version).
3. Run regression tests, build all needed native packages from one clean commit,
   and use `packaging/assemble_release.py --output releases/<new-id>` under
   `dashboard/customer`. Preserve old release directories.
4. Check desktop launch and physical USB behavior on both PCB v2/v3: connect/reconnect,
   dual/no/single-tag reads, recovery, Live View, history/range and configuration
   persistence. Use expendable data for destructive checks.
5. Create the next simple customer ZIP and a new delivery record with exact hashes,
   previous delivery ID, changes, required updates and validation evidence. Tag its
   reviewed commit; send the new ID and retain previous artifacts for rollback.

A rollback means reinstalling a previously identified artifact. Firmware rollback
also needs a tested flashing procedure and storage/configuration compatibility;
do not promise that a source tag alone makes downgrade safe.

## Promoting experimental firmware and mobile

The delivered USB contract supports dual `readnow`, status, configuration and
history. It lacks `protocol`/`readant`. The experimental pair introduces
`RFID_PROTOCOL_V2` and individual-antenna commands. Capability negotiation and
backward parsing are implementation details to verify, not proof of a supported pair.
See `mobile_app/MOBILE_BLE_PROTOCOL_CONTRACT.md` for the experimental BLE contract;
some sections are historical plans rather than delivered behavior.

Before promoting any local firmware, give its exact committed source a distinct
version and test it with the customer dashboard, original local dashboard and
mobile app. Include USB behavior, BLE framing/transfers/completion, both antennas,
idle/sleep/battery behavior, configuration and existing stored records on PCB v2/v3.
Also test the mobile app with delivered firmware if legacy support is claimed;
unsupported features must stay disabled. Until then, every experimental pairing
is recorded as unverified and mobile remains excluded from customer deliveries.

Changes required by mobile must not silently change USB commands, flash layout,
UUIDs or existing customer behavior. Coordinate shared firmware changes between
the customer/dashboard and mobile development sessions. Maintain the tested pair
matrix and required capabilities in each new delivery record, with independent
component tags and one overall delivery tag.
