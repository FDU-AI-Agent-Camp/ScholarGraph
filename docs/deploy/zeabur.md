# Zeabur 部署指南（一体镜像 + GROBID 旁路）

本文说明如何将 ScholarGraph 以**单服务一体镜像**部署到 [Zeabur](https://zeabur.com)，并与独立的 GROBID 服务内网互通。

## 架构

```text
公网 HTTPS
    │
    ▼
ScholarGraph 一体服务（本仓库 Dockerfile）
  · Vue 静态页（同源 /）
  · FastAPI（/api/v1、/docs）
  · MinerU（短 PDF）
  · Volume: /app/data
    │
    │ 内网 HTTP :8070（勿配公网域名）
    ▼
GROBID 独立服务
  镜像: grobid/grobid:0.9.0-crf
```

## 1. GROBID 服务（Docker Hub）

1. Create Service → **Deploy from Docker Image**
2. 镜像：`grobid/grobid:0.9.0-crf`
3. Port：**8070**，协议：**HTTP**（TCP 上的 HTTP，非 UDP）
4. 资源建议：≥ **2 vCPU / 4–6 GB RAM**
5. **不要**绑定 Public Domain
6. 可选健康检查：`GET /api/isalive`（端口 8070），initial delay 60–120s
7. **无需**持久卷；**无需**自定义启动命令（用镜像默认 ENTRYPOINT）
8. **无需**业务环境变量（复杂调优请挂 `grobid.yaml`，一般不必）

记下 Zeabur **Networking** 中的内网地址，例如 `http://grobid.zeabur.internal:8070`。

## 2. 主服务（本仓库）

1. Create Service → 绑定本 Git 仓库（根目录有 `Dockerfile`，Zeabur 会自动用 Docker 构建）
2. **Volumes**：添加云盘，Mount Path = **`/app/data`**，建议 ≥ **20–40 GB**
3. Port：容器监听 **`$PORT`**（entrypoint 默认 8080）；在 Zeabur 按平台提示映射公网域名
4. 健康检查（可选）：`GET /api/v1/health`

### 2.1 推荐环境变量

| 变量 | 示例值 | 说明 |
|------|--------|------|
| `APP_PROFILE` | `prod` | 必填；镜像默认已是 `prod` |
| `APP_ENV` | `production` | |
| `DEBUG` | `false` | |
| `LLM_MODE` | `live` | 生产推理 |
| `SCHOLARGRAPH_API_KEY` | *(密钥)* | MaaS / LLM Key |
| `LLM_API_BASE_URL` | `https://api.modelarts-maas.com/v2` | |
| `LLM_MODEL_PRIMARY` | *(控制台模型名)* | |
| `LLM_MODEL_FALLBACK` | *(控制台模型名)* | |
| `EMBEDDING_API_BASE_URL` | `https://api.modelarts-maas.com/v1` | |
| `EMBEDDING_API_KEY` | *(密钥)* | 可与主 Key 相同视网关而定 |
| `EMBEDDING_MODEL` | `bge-m3` | |
| `RERANKER_ENABLED` | `true` | prod 硬性要求 |
| `RERANKER_MODEL` | `bge-reranker-v2-m3` | |
| `RERANKER_API_BASE_URL` | `https://api.modelarts-maas.com/v1` | |
| `RERANKER_API_KEY` | *(密钥)* | |
| `GROBID_URL` | `http://<内网主机>:8070` | **须含协议与端口** |
| `INGEST_ROUTE` | `auto` | 短文 MinerU，长文 GROBID |
| `INGEST_MINERU_ENABLED` | `true` | |
| `CORS_ORIGINS` | `https://你的公网域名` | 同源也可填公网域名 |
| `DATABASE_URL` | `sqlite:////app/data/scholargraph.db` | 镜像默认 |
| `GRAPH_DATA_DIR` | `/app/data/graphs` | 镜像默认 |
| `UPLOAD_DIR` | `/app/data/uploads` | 镜像默认 |
| `CHROMADB_PATH` | `/app/data/chroma` | 镜像默认 |
| `HF_HOME` | `/app/data/models/huggingface` | 模型缓存进 Volume |
| `MODELSCOPE_CACHE` | `/app/data/models/modelscope` | 同上 |
| `INGEST_MINERU_MODEL_SOURCE` | `modelscope` | |

镜像已写入上述路径类默认值；密钥与 `GROBID_URL` / CORS 务必在控制台覆盖。

### 2.2 Volume 目录约定

挂载 `/app/data` 后，持久化内容包括：

```text
/app/data/
  scholargraph.db
  graphs/
  uploads/
  chroma/
  models/huggingface/
  models/modelscope/
```

首次启动 MinerU 会向 `models/` 下载权重（可能较久）。之后重启/重新部署只要 Volume 还在，即可跳过重复下载。

## 3. 本地验证镜像（可选）

在仓库根目录：

```bash
docker build -t scholargraph:local .
docker run --rm -p 8080:8080 \
  -e APP_PROFILE=ci \
  -e LLM_MODE=mock \
  -e RERANKER_ENABLED=false \
  -e SCHOLARGRAPH_IGNORE_DOTENV=1 \
  -v scholargraph-data:/app/data \
  scholargraph:local
```

说明：`APP_PROFILE=prod` 会强制 Reranker；本地 mock 冒烟请用 `ci` + `LLM_MODE=mock`。

浏览器打开 `http://localhost:8080/`，API 文档 `http://localhost:8080/docs`，健康检查 `http://localhost:8080/api/v1/health`。

## 4. 构建注意

- 镜像含 `uv sync --extra mineru`，体积大、构建时间长，属预期。
- Zeabur 无状态：不要在 SSH 里手动 pip / 下载模型到容器可写层；模型必须落在 `/app/data/models`。
- 推送代码或改环境变量会触发重建；Volume 数据保留。

## 5. 相关文件

| 文件 | 作用 |
|------|------|
| `Dockerfile` | 多阶段：前端 build + Python/MinerU + SPA |
| `.dockerignore` | 缩小构建上下文 |
| `zbpack.json` | 指定根目录 Dockerfile |
| `scripts/docker-entrypoint.sh` | 建目录 → Alembic → uvicorn |
| `backend/startup/spa_static.py` | 托管 `frontend/dist` |
