# Repository guide

## Purpose

RH Install Manager is an interactive terminal tool for installing, updating,
and managing RotorHazard on Raspberry Pi. It also configures the host system,
flashes Arduino-based timing nodes, manages network hotspot modes, and updates
itself.

## Main flow

- `rhim.sh` checks dependencies and starts the application.
- `start_rhim.py` checks the Python version and enters `update.py`.
- `update.py` owns the main menus and routes operations.
- `rpi_update.py` coordinates RotorHazard installation and updates.
- Shell scripts in `scripts/` perform system changes, downloads, backups,
  service setup, and network configuration.
- `nodes_flash.py` handles Arduino node firmware through UART with I2C or GPIO
  reset control.

## Configuration and state

- `updater-config.json` is generated locally from `distr-updater-config.json`
  and stores the selected RotorHazard source and hardware settings.
- `~/.rhim_markers/rhim_config.json` records completed setup and installation
  stages so work can continue after a reboot.
- `version.txt` links the RHIM release to its supported stable RotorHazard
  version, beta version, and bundled node firmware API level.
- Do not confuse this repository's branches with the RotorHazard source chosen
  in the wizard. The `main` option targets the separate RotorHazard repository.
- Readers use line positions in `version.txt`. Preserve that layout and keep
  stable and beta targets independent; main and custom remain separate choices.
- `docs/update-notes.txt` is release history. Add relevant entries without
  rewriting version references in older entries.

## Development conventions

- Read the affected files and nearby conventions before editing. Follow their
  naming, formatting, error handling, and existing helpers.
- Work within the procedural Python, shell, and JSON structure. Prefer a small
  fix in the shared path used by affected callers. Refactor when the task needs
  it, and keep unrelated cleanup out of functional commits.
- Keep RHIM's runtime requirements separate from those of the selected
  RotorHazard release. Preserve declared Python and shell compatibility.
- Check the changed path, its callers, and invoked scripts together. For an
  installation or update change, inspect the Python coordinator and the shell
  scripts involved before editing.

## Installation and recovery

- Treat fresh installation, updating an existing installation, and resuming
  after reboot or failure as equally important paths.
- Do not silently switch or recreate an interpreter, virtual environment, or
  service. Make any required migration an explicit step agreed within the task.
- Check critical operations and propagate failures. Report success and record
  a completion marker only after confirming that the stage succeeded.
- Distinguish an absent optional file from a real read, copy, or command error.
  Preserve useful error details so a failed stage can be diagnosed and resumed.
- Before adding broad shell error handling such as `set -e`, inspect affected
  paths, including commands whose nonzero status is expected.
- Preserve host-update functionality and other behavior outside the edit's
  scope. Account for system package effects, report stage failures, and state
  when a restart or reboot is required.

## Data preservation

- Locate the installation's actual data before changing or backing it up.
  Check legacy `src/server`, `~/rh-data`, and external locations configured
  through `datapath.ini` or `--data`, as applicable to the selected release.
- Preserve configuration, databases, user images, plugins, and backups at the
  paths the installation uses. Copying `datapath.ini` alone does not preserve
  the data it points to. Keep existing backup logic working.
- A copy of RotorHazard source does not restore a virtual environment, host
  changes, or database migrations. Describe recovery limits; do not promise
  automatic rollback without an implemented and verified recovery path.

## Verification

- Add a small, meaningful test for new nontrivial logic and bug fixes. If a
  relevant test cannot run, document the limitation and the missing check.
- Keep tests separate from production actions. Use the smallest check that
  verifies the intended effect, and report its scope and result.
- Distinguish local unit or syntax checks, isolated shell tests, real Linux
  execution, and Raspberry Pi hardware checks. Passing a lower level does not
  prove behavior on hardware. These are verification levels, not a claim that
  the repository already provides a test suite for each level.
- System-changing scripts belong only in the target or test environment
  designated by the task. They can change packages, services, networking,
  hardware interfaces, and files outside the checkout.
- `debug_mode` helps with non-Pi inspection but does not isolate shell-side
  effects. Changing `HOME` does not isolate explicit `/home/$user` paths or
  commands run through `sudo`.
