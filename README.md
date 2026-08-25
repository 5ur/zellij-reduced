This repository builds a small customized Zellij from upstream main

- reads and checks out the current main commit
- applies `patches/*.patch` in order
- rebuilds the modified built-in bar plugins
- builds Linux and macOS binaries using upstream's locked dependencies
- publishes a GitHub Release

### Patches

[0001-ui-and-session-names.patch](./patches/0001-ui-and-session-names.patch)

- removes the persistent `Zellij` label from the default and compact bars
- keeps session names visible
- changes automatic session names to `session-<pid>`, with numeric suffixes on collision
- manual session names, attach/resurrection behavior, and the plugin random-name API are unchanged.

[0002-disable-web-capability.patch](./patches/0002-disable-web-capability.patch)

- removes `web_server_capability` from Zellij's default Cargo features without deleting the web implementation

### Optimized builds are

- Linux: `x86_64-unknown-linux-musl`, `target-cpu=x86-64-v4`
- macOS: `aarch64-apple-darwin`, `target-cpu=apple-m5`

The workflow verifies that the upstream Rust toolchain recognizes the requested CPU target
If an upstream change makes a patch stale there's an apply --check that fails before the build starts
