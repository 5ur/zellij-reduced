This repository builds a small customized [Zellij](https://github.com/zellij-org/zellij) from upstream main.

- resolves upstream main once and checks out that exact commit on both platforms
- applies every `patches/*.patch` in filename order
- rebuilds all bundled plugin assets, including changes to shared plugin code
- builds Linux and macOS binaries using upstream's locked dependencies
- publishes a GitHub Release with checksums and links to the upstream and patch-set revisions

### Enable or disable a change

Add a `*.patch` file to `patches/` to enable it. Delete it, or rename it to
`*.patch.disabled`, to disable it. Number filenames to control application order.
Only files directly inside `patches/` ending in `.patch` are applied.

Commit and push the desired set, then run **Build custom Zellij** from GitHub
Actions on that revision. No workflow edit or local Rust installation is needed.
Each run starts from a fresh upstream checkout; removing a patch removes its
effect from the next build. Existing installed binaries and releases are unchanged.

An empty or absent `patches/` directory is supported: it builds unmodified
upstream sources, including upstream branding, session naming, and web support.
A stale patch or a patch whose dependency was removed fails before compilation;
patches are never silently skipped. Upstream main can change between runs.

### Patches

[0001-remove-bar-label.patch](./patches/0001-remove-bar-label.patch)

- replaces the persistent `Zellij` label in the default and compact bars with a separating space
- keeps session names and the existing width calculation
- does not change the outer terminal/window title or other screens

[0002-disable-web-capability.patch](./patches/0002-disable-web-capability.patch)

- removes `web_server_capability` from Zellij's default Cargo features
- disables the built-in browser/web server in this workflow's binary build
- leaves the web implementation in source and leaves plugin HTTP/network capabilities available

[0003-session-names.patch](./patches/0003-session-names.patch)

- changes automatic session names to `session-<pid>`, with numeric suffixes on collision
- retains checks against both live and resurrectable sessions and the 1,000-candidate limit
- leaves manual names and the plugin random-name API unchanged

The label and session-name patches were split from the original
`0001-ui-and-session-names.patch` without changing their combined source diff.
They can now be disabled independently. A session name is not a reliable marker
for terminal shortcut routing because it is user-editable and naming differs upstream.

### Plugin embedding

Release binaries embed `zellij-utils/assets/plugins/*.wasm`. Applying a plugin's
source patch alone does not update those bytes. The workflow discovers these
assets, rebuilds their matching `default-plugins/<name>` packages together, and
copies every rebuilt asset before compiling the binary. Missing sources or build
outputs fail the job.

This deliberately rebuilds all bundled plugins on each run, including with no
patches. It costs CI compilation time but avoids maintaining a list of affected
plugins or overlooking a shared dependency. CPU optimization flags apply only to
the final native build, not to the WASM plugin build.

### Terminal title marker

[0004-terminal-title-marker.patch](./patches/0004-terminal-title-marker.patch)
changes one formatting string in `make_terminal_title` in
`zellij-utils/src/shared.rs`. The title becomes `󰷟 session | pane title` (or
`󰷟 session` without a pane title). The marker is followed by one space. Session
names, pane/editor title suffixes, and the OSC title-setting sequence are preserved.
This is separate from the bar label and session naming.

Hammerspoon's `config/bindings/zellij.lua` matches the prefix inside Kitty, then
can narrow a rule by the focused pane's title suffix, such as ` — ` for Neovim.
The new marker appears only after installing a binary built with this patch and
starting/attaching through that version; it cannot be added by reloading dotfiles.
Existing sessions may retain their old server binary, so use a fresh session for
validation before replacing existing sessions.

Unpatched upstream currently has no fixed Zellij title prefix. A future switch
back therefore needs an explicitly marked session name or another verified
detection method; changing a matcher alone cannot manufacture that marker.

### Optimized builds

- Linux: `x86_64-unknown-linux-musl`, `target-cpu=x86-64-v4`
- macOS: `aarch64-apple-darwin`, `target-cpu=apple-m5`

These binaries target those CPUs, rather than all Linux or macOS machines. The
workflow checks that the upstream Rust toolchain recognizes the requested target.

### Local workflow checks

```sh
python3 -B -m unittest discover -s tests -v
```

The tests execute the workflow's patch shell against disposable Git repositories
and check plugin discovery/copying with a fake Cargo command. They require Python,
Bash, and Git, with no Rust installation or network access. Actual compilation
and binary behavior still need validation by a GitHub Actions build.
