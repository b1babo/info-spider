from pydantic import BaseModel, Field, HttpUrl,field_validator, model_validator
from typing import Any, List, Literal, Optional, Dict, Union
from datetime import datetime, timezone
import os
# ====================
# 1. 输出数据模型 (存储的数据)
# ====================

class MyBase(BaseModel):
    # create_time: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    # update_time: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    pass 


class Analytics(MyBase):
    view_count: int  = 0
    like_count: int  = 0
    reply_count : int = 0
    share_count : int = 0
    bookmark_count : int = 0
    referenced_count : int = 0

class Author(BaseModel):
    id: str = ""

    author_url: str = ""
    author_name : str = ""
    author_display_name : str  = ""

    following_count: int = 0
    followers_count : int = 0
    description : str = ""

class ResourceMedia(MyBase):
    media_type : str = ""
    media_url : str = ""



class ResourceBase(MyBase):
    id: str = ""
    # share original conversation
    resource_type :str = "original"
    resource_url : str = ""
    resource_content: str = ""

    resource_author_name : str = ""
    resource_author_display_name: str = ""
    resource_author_url : str  = ""

    resource_platform: str  = ""
    resource_platform_url: str  = ""

    urls: List = Field(default_factory=list)

    
    resource_media :List[ResourceMedia] = Field(default_factory=list)
    hashtags: List[str] = Field(default_factory=list)

    resource_create_time: Optional[str] = None
    resource_update_time: Optional[str] = None


    is_pinned : bool  = False
    analytics : Analytics = Field(default_factory=Analytics)


class Comment(ResourceBase):
    pass 

class Resource(ResourceBase):
    description : str = ""
    reference_resource : List = Field(default_factory=list)
    share_resource : List = Field(default_factory=list)
    conversation_resource : List = Field(default_factory=list)

    comment_resource : List = Field(default_factory=list)
    

# ====================
# 2. 配置输入模型 (YAML校验)
# ====================

class ActionConfig(BaseModel):
    """Action 配置"""
    enabled: bool = Field(default=True, description="是否启用此 action")
    action: str = Field(..., description="Action 名称")
    params: Dict[str, Any] = Field(default_factory=dict, description="Action 参数")


class TaskConfig(BaseModel):
    enable: bool = False
    name: str = Field(..., description="任务名称，方便日志记录")
    url: str = Field(..., description="起始URL")
    actor: str = Field(..., description="指定使用的 Actor 类名，e.g. 'TwitterUserParser'")
    # 可以传递给插件的额外参数，比如滚动次数、最大抓取条数
    params: dict = Field(default_factory=dict)

    use_profile: str = Field(..., description="关联的 profile 名称")

    actions: List[ActionConfig] = Field(
        default_factory=list,
        description="预定义的 Action 列表"
    )

class Profile(BaseModel):


    name: str = Field(..., description="配置名称")

    # 运行模式
    mode: Literal["browser", "api"] = Field("browser", description="运行模式：browser(连接浏览器) 或 api(纯API请求)")

    # 浏览器模式字段
    port: Optional[int] = Field(None, description="远程调试端口")
    browser_host: Optional[str] = Field("localhost", description="浏览器主机地址（支持远程 IP 或域名）")
    browser_type: str = Field("msedge", description="msedge 或 chrome")

    # API 模式字段
    proxy: Optional[str] = Field(None, description="代理服务器地址 (格式: http://host:port 或 socks5://host:port)")

    params: Dict[str, Any] = Field(default_factory=dict, description="额外的扩展配置参数，如代理、超时设置等")


    @model_validator(mode='after')
    def check_mode_requirements(self):
        if self.mode == 'browser':
            if not self.port:
                raise ValueError("在 'browser' 模式下，必须配置 'port'")
        return self


class AppConfig(BaseModel):
    profiles: List[Profile]
    tasks: List[TaskConfig] # 对应 YAML 中的 tasks 列表

    def get_profile(self, name: str) -> Optional[Profile]:
        for p in self.profiles:
            if p.name == name:
                return p
        return None

    def get_task(self, name: str) -> Optional[TaskConfig]:
        for t in self.tasks:
            if t.name == name:
                return t
        return None