"""配置默认值定义。

定义系统中使用的默认配置值。
"""

from core.config.schema import MaintenanceConfig, MaintenanceMode

DEFAULT_MAINTENANCE_CONFIG = MaintenanceConfig(
    mode=MaintenanceMode.WARN,
    prune_after_ms=7 * 24 * 60 * 60 * 1000,
    max_entries=10000,
    rotate_bytes=100 * 1024 * 1024,
    max_disk_bytes=None,
    high_water_bytes=None,
)
"""默认维护配置。

默认配置说明：
- mode: WARN 模式，仅记录警告，不自动清理
- prune_after_ms: 7 天（604,800,000 毫秒）
- max_entries: 10,000 条记录
- rotate_bytes: 100 MB 日志轮转阈值
- max_disk_bytes: 不限制磁盘使用
- high_water_bytes: 不设置高水位警告
"""
