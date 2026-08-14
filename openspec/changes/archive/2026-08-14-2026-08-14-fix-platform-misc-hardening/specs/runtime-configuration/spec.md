## ADDED Requirements

### Requirement: 生产环境关闭交互式 API 文档

`APP_ENV=production` 时，系统 MUST NOT 注册 `/docs`、`/redoc`、`/openapi.json` 交互式文档路由；其他环境保持可用以便开发调试。

#### Scenario: 生产环境访问文档 404

- GIVEN APP_ENV=production
- WHEN 访问 GET /docs
- THEN 响应 SHALL 为 404
