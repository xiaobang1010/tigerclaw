"""浏览器服务模块。

提供浏览器控制、自动化操作和 Profile 管理功能。

参考实现: openclaw/src/browser/
"""

from browser.config import (
    BrowserConfig,
    BrowserControlAuth,
    BrowserDriverType,
    BrowserProfile,
    resolve_browser_config,
    create_default_profiles,
)
from browser.types import (
    BrowserActionResult,
    BrowserElement,
    BrowserSnapshot,
    BrowserTab,
)
from browser.cdp import (
    CdpClient,
    CdpTarget,
    CdpVersion,
    CdpError,
    CdpTimeoutError,
    is_cdp_reachable,
    AriaSnapshotNode,
    DomSnapshotNode,
)
from browser.chrome import (
    BrowserLauncher,
    BrowserExecutable,
    RunningBrowser,
    BrowserLaunchError,
    find_chrome_executable,
    allocate_cdp_port,
    allocate_color,
    is_valid_profile_name,
)
from browser.profiles import (
    BrowserProfilesService,
    ProfileStatus,
    CreateProfileResult,
    DeleteProfileResult,
    ProfileError,
)
from browser.tabs import (
    TabManager,
    AutomationEngine,
    TabInfo,
    NavigateResult,
    ClickResult,
    TypeResult,
    ScreenshotResult,
    SnapshotResult,
    AutomationError,
)
from browser.server import (
    BrowserControlServer,
    BrowserServerState,
    start_browser_control_server,
)

__all__ = [
    "BrowserConfig",
    "BrowserControlAuth",
    "BrowserDriverType",
    "BrowserProfile",
    "resolve_browser_config",
    "create_default_profiles",
    "BrowserTab",
    "BrowserSnapshot",
    "BrowserElement",
    "BrowserActionResult",
    "CdpClient",
    "CdpTarget",
    "CdpVersion",
    "CdpError",
    "CdpTimeoutError",
    "is_cdp_reachable",
    "AriaSnapshotNode",
    "DomSnapshotNode",
    "BrowserLauncher",
    "BrowserExecutable",
    "RunningBrowser",
    "BrowserLaunchError",
    "find_chrome_executable",
    "allocate_cdp_port",
    "allocate_color",
    "is_valid_profile_name",
    "BrowserProfilesService",
    "ProfileStatus",
    "CreateProfileResult",
    "DeleteProfileResult",
    "ProfileError",
    "TabManager",
    "AutomationEngine",
    "TabInfo",
    "NavigateResult",
    "ClickResult",
    "TypeResult",
    "ScreenshotResult",
    "SnapshotResult",
    "AutomationError",
    "BrowserControlServer",
    "BrowserServerState",
    "start_browser_control_server",
]
