"""Ordered JavaScript modules embedded in the standalone dashboard artifact."""

RUNTIME_MODULES = (
    (
        "lifecycle",
        r"""
        window.createDashboardRuntime = function createDashboardRuntime(initialConfig) {
            return {
                config: initialConfig || null,
                app: null,
                root: null,
                mount(root = document, config = this.config) {
                    if (this.app?._mounted) return this.app;
                    this.root = root;
                    this.config = config || window.DASHBOARD_CONFIG;
                    this.app = new DashboardApp(this.config);
                    this.app.root = root;
                    window.App = this.app;
                    return this.app.init();
                },
                update(config, root = this.root || document) {
                    this.destroy();
                    return this.mount(root, config);
                },
                destroy() {
                    this.app?.destroy();
                    this.app = null;
                    this.root = null;
                }
            };
        };
""",
    ),
    (
        "bootstrap",
        r"""
        function bootApp() {
            if (window.DASHBOARD_CONFIG && !window.App) {
                window.DashboardRuntime = window.createDashboardRuntime(window.DASHBOARD_CONFIG);
                window.DashboardRuntime.mount(document);
            }
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', bootApp, { once: true });
        } else {
            bootApp();
        }
""",
    ),
)


def render_runtime_bundle():
    """Compose runtime modules in their declared dependency order."""
    return "\n".join(
        f"        // runtime:{name}\n{source.strip()}" for name, source in RUNTIME_MODULES
    )
