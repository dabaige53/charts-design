"""Ordered JavaScript modules embedded in the standalone dashboard artifact."""

RUNTIME_MODULES = (
    (
        "lifecycle",
        r"""
        window.getDashboardAppForElement = function getDashboardAppForElement(element) {
            let node = element;
            while (node) {
                if (node.__dashboardApp) return node.__dashboardApp;
                node = node.parentNode || node.host || null;
            }
            return window.App || null;
        };

        window.createDashboardRuntime = function createDashboardRuntime(initialConfig, root = document) {
            return {
                config: initialConfig || null,
                app: null,
                root,
                mount(root = this.root, config = this.config) {
                    if (this.app?._mounted) return this.app;
                    this.root = root;
                    this.config = config || window.DASHBOARD_CONFIG;
                    this.app = new DashboardApp(this.config, root);
                    if (root === document) window.App = this.app;
                    return this.app.init();
                },
                update(config, root = this.root) {
                    this.destroy();
                    return this.mount(root, config);
                },
                destroy() {
                    const app = this.app;
                    app?.destroy();
                    if (window.App === app) window.App = null;
                    this.app = null;
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
                window.DashboardRuntime = window.createDashboardRuntime(window.DASHBOARD_CONFIG, document);
                window.DashboardRuntime.mount();
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
