"""测试夹具：禁用鉴权中间件，方便已有 API 测试继续在无登录态下跑."""
import os

# 必须在导入 server.app 之前设置
os.environ["PEBS_DISABLE_AUTH"] = "1"
