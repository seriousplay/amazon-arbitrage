"""
应用异常体系 - 自定义异常类

定义清晰的异常层次结构，替代通用的 Exception：
- 提高错误处理的一致性
- 便于按异常类型进行分类处理
- 提供更多上下文信息（错误码、详情）
- 支持国际化错误消息
"""

from typing import Optional, Dict, Any


class AppError(Exception):
    """
    应用异常基类

    所有业务异常的父类，提供统一的错误信息结构。

    Attributes:
        message: 人类可读的错误描述
        code: 机器可读的错误码（可用于前端展示、日志分类）
        details: 额外的错误详情（用于调试或高级错误处理）
    """

    def __init__(
        self,
        message: str,
        code: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict:
        """转换为字典格式（用于 API 响应）"""
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "code": self.code,
            "details": self.details,
        }

    def __str__(self) -> str:
        return f"{self.__class__.__name__}[{self.code}]: {self.message}"


# ============ 爬虫相关异常 ============


class ScrapingError(AppError):
    """爬取过程中的基础异常"""

    def __init__(self, message: str, code: str = "SCRAPING_ERROR", **kwargs):
        super().__init__(message, code, **kwargs)


class NetworkError(ScrapingError):
    """网络请求失败（超时、连接错误、HTTP 错误等）"""

    def __init__(self, message: str, code: str = "NETWORK_ERROR", **kwargs):
        super().__init__(message, code, **kwargs)


class ParseError(ScrapingError):
    """页面解析失败（HTML 结构变化、数据提取失败等）"""

    def __init__(self, message: str, code: str = "PARSE_ERROR", **kwargs):
        super().__init__(message, code, **kwargs)


class BlockedError(ScrapingError):
    """被反爬虫机制拦截"""

    def __init__(
        self, message: str = "访问被阻止，可能需要验证码或更换 IP", code: str = "BLOCKED", **kwargs
    ):
        super().__init__(message, code, **kwargs)


# ============ 验证码相关异常 ============


class CaptchaError(AppError):
    """验证码相关异常基类"""

    def __init__(self, message: str, code: str = "CAPTCHA_ERROR", **kwargs):
        super().__init__(message, code, **kwargs)


class CaptchaSolveFailed(CaptchaError):
    """验证码解决失败"""

    def __init__(self, message: str = "验证码解决失败", **kwargs):
        super().__init__(message, code="CAPTCHA_SOLVE_FAILED", **kwargs)


class CaptchaTimeout(CaptchaError):
    """验证码解决超时"""

    def __init__(self, message: str = "验证码解决超时", **kwargs):
        super().__init__(message, code="CAPTCHA_TIMEOUT", **kwargs)


# ============ 匹配相关异常 ============


class MatchingError(AppError):
    """匹配过程中的异常"""

    def __init__(self, message: str, code: str = "MATCHING_ERROR", **kwargs):
        super().__init__(message, code, **kwargs)


class NoMatchFoundError(MatchingError):
    """未找到匹配的商品"""

    def __init__(self, message: str = "未找到匹配的商品", **kwargs):
        super().__init__(message, code="NO_MATCH_FOUND", **kwargs)


class LowConfidenceMatchError(MatchingError):
    """匹配置信度过低"""

    def __init__(self, message: str = "匹配置信度过低", score: Optional[float] = None, **kwargs):
        details = kwargs.pop("details", {})
        if score is not None:
            details["score"] = score
        super().__init__(message, code="LOW_CONFIDENCE_MATCH", details=details, **kwargs)


# ============ 验证/校验相关异常 ============


class ValidationError(AppError):
    """数据验证失败"""

    def __init__(
        self, message: str, field: Optional[str] = None, code: str = "VALIDATION_ERROR", **kwargs
    ):
        details = kwargs.pop("details", {})
        if field:
            details["field"] = field
        super().__init__(message, code, details=details, **kwargs)


class InvalidInputError(ValidationError):
    """输入参数无效"""

    def __init__(self, message: str = "输入参数无效", field: Optional[str] = None, **kwargs):
        super().__init__(message, code="INVALID_INPUT", field=field, **kwargs)


class MissingRequiredFieldError(ValidationError):
    """缺少必填字段"""

    def __init__(self, field: str, **kwargs):
        message = f"缺少必填字段: {field}"
        super().__init__(message, field=field, code="MISSING_REQUIRED_FIELD", **kwargs)


# ============ 资源相关异常 ============


class ResourceError(AppError):
    """资源相关异常基类"""

    def __init__(self, message: str, code: str = "RESOURCE_ERROR", **kwargs):
        super().__init__(message, code, **kwargs)


class ResourceNotFoundError(ResourceError):
    """资源不存在"""

    def __init__(self, resource_type: str, resource_id: str, **kwargs):
        message = f"{resource_type} 不存在: {resource_id}"
        details = kwargs.pop("details", {})
        details.update({"resource_type": resource_type, "resource_id": resource_id})
        super().__init__(message, code="RESOURCE_NOT_FOUND", details=details, **kwargs)


class ResourceConflictError(ResourceError):
    """资源冲突（如任务已存在、状态冲突等）"""

    def __init__(self, message: str, resource_type: Optional[str] = None, **kwargs):
        details = kwargs.pop("details", {})
        if resource_type:
            details["resource_type"] = resource_type
        super().__init__(message, code="RESOURCE_CONFLICT", details=details, **kwargs)


class QuotaExceededError(ResourceError):
    """配额超限（如 API 调用次数超限、并发任务数超限等）"""

    def __init__(self, message: str = "配额超限", quota_type: Optional[str] = None, **kwargs):
        details = kwargs.pop("details", {})
        if quota_type:
            details["quota_type"] = quota_type
        super().__init__(message, code="QUOTA_EXCEEDED", details=details, **kwargs)


# ============ 业务逻辑异常 ============


class BusinessError(AppError):
    """业务逻辑异常基类"""

    def __init__(self, message: str, code: str = "BUSINESS_ERROR", **kwargs):
        super().__init__(message, code, **kwargs)


class TaskCancelledError(BusinessError):
    """任务被取消"""

    def __init__(self, task_id: str, **kwargs):
        message = f"任务已取消: {task_id}"
        details = kwargs.pop("details", {})
        details["task_id"] = task_id
        super().__init__(message, code="TASK_CANCELLED", details=details, **kwargs)


class TaskTimeoutError(BusinessError):
    """任务执行超时"""

    def __init__(self, task_id: str, timeout: Optional[int] = None, **kwargs):
        message = f"任务执行超时: {task_id}"
        if timeout:
            message += f"（超时时间: {timeout}秒）"
        details = kwargs.pop("details", {})
        details["task_id"] = task_id
        if timeout:
            details["timeout"] = timeout
        super().__init__(message, code="TASK_TIMEOUT", details=details, **kwargs)


class InvalidStateError(BusinessError):
    """状态无效（如在错误的状态下执行操作）"""

    def __init__(
        self,
        message: str,
        current_state: Optional[str] = None,
        expected_state: Optional[str] = None,
        **kwargs,
    ):
        details = kwargs.pop("details", {})
        if current_state:
            details["current_state"] = current_state
        if expected_state:
            details["expected_state"] = expected_state
        super().__init__(message, code="INVALID_STATE", details=details, **kwargs)


# ============ 配置相关异常 ============


class ConfigurationError(AppError):
    """配置错误"""

    def __init__(
        self, message: str, config_key: Optional[str] = None, code: str = "CONFIG_ERROR", **kwargs
    ):
        details = kwargs.pop("details", {})
        if config_key:
            details["config_key"] = config_key
        super().__init__(message, code, details=details, **kwargs)


class MissingConfigError(ConfigurationError):
    """缺少必要的配置项"""

    def __init__(self, config_key: str, **kwargs):
        message = f"缺少必要的配置项: {config_key}"
        super().__init__(message, config_key=config_key, code="MISSING_CONFIG", **kwargs)


class InvalidConfigError(ConfigurationError):
    """配置项值无效"""

    def __init__(self, config_key: str, value: Any, reason: str, **kwargs):
        message = f"配置项 {config_key} 值无效 ({value}): {reason}"
        details = kwargs.pop("details", {})
        details["value"] = str(value)
        super().__init__(
            message, config_key=config_key, code="INVALID_CONFIG", details=details, **kwargs
        )


# ============ 数据库相关异常 ============


class DatabaseError(AppError):
    """数据库操作异常基类"""

    def __init__(self, message: str, code: str = "DATABASE_ERROR", **kwargs):
        super().__init__(message, code, **kwargs)


class DatabaseConnectionError(DatabaseError):
    """数据库连接失败"""

    def __init__(self, message: str = "数据库连接失败", **kwargs):
        super().__init__(message, code="DATABASE_CONNECTION_ERROR", **kwargs)


class DatabaseQueryError(DatabaseError):
    """数据库查询失败"""

    def __init__(self, message: str, query: Optional[str] = None, **kwargs):
        details = kwargs.pop("details", {})
        if query:
            details["query"] = query[:200]  # 限制长度
        super().__init__(message, code="DATABASE_QUERY_ERROR", details=details, **kwargs)


# ============ 便捷函数 ============


def wrap_external_exception(
    exc: Exception,
    message: str,
    code: str,
    details: Optional[Dict[str, Any]] = None,
) -> AppError:
    """
    将外部异常包装为 AppError

    用于在捕获第三方库异常时，统一转换为应用异常。

    Args:
        exc: 原始异常
        message: 用户友好的错误描述
        code: 错误码
        details: 额外详情

    Returns:
        包装后的 AppError
    """
    details = details or {}
    details["original_exception"] = exc.__class__.__name__
    details["original_message"] = str(exc)
    return AppError(message=message, code=code, details=details)
