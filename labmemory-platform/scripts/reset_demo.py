"""重置演示数据：清除业务数据 → 通过 /v1 API 重新注入演示场景。

保留：用户账号、项目、实验及其成员。
清除：会议、候选、主张、任务、审计、结果、审计事件。
重新注入：通过 mock_feishu_push 调用 /v1 接口推送演示场景（走真实飞书集成链路）。

使用方式：
    # 先启动后端
    conda run -n labmemory uvicorn app.main:app --port 8081

    # 重置 + 重新 seed
    python -m scripts.reset_demo

    # 仅清除，不重新注入
    python -m scripts.reset_demo --clear-only

    # 仅重置数据库（不依赖后端运行，直接清库 + seed_demo.py 原逻辑）
    python -m scripts.reset_demo --db-only
"""
from __future__ import annotations

import argparse
import sys

from app.db.base import Base
from app.db.models import (
    ActionAudit,
    AuditEvent,
    Candidate,
    Claim,
    Meeting,
    MeetingReview,
    Result,
    Task,
)
from app.db.session import SessionLocal, engine


def clear_business_data() -> None:
    """清除所有业务数据（会议/候选/主张/任务/审计/结果/事件 + RAG 索引），保留账号、项目、实验。"""
    db = SessionLocal()
    try:
        # 按依赖顺序删除（外键约束）
        db.query(Result).delete()
        db.query(ActionAudit).delete()
        db.query(Task).delete()
        db.query(Claim).delete()
        db.query(Candidate).delete()
        db.query(MeetingReview).delete()
        db.query(Meeting).delete()
        db.query(AuditEvent).delete()
        # 清空 RAG 索引（业务数据已清，索引也应清空，否则 QA 读取过期引用）
        try:
            from app.db.models import EmbeddingChunk
            db.query(EmbeddingChunk).delete()
            conn = db.connection().connection
            conn.execute("DELETE FROM vec_chunks")
            conn.execute("DELETE FROM chunks_fts")
            conn.commit()
        except Exception:
            pass
        db.commit()
        print("✓ 已清除所有业务数据")
        print("  - 会议、复核、候选")
        print("  - 主张、参数版本")
        print("  - 任务、行动审计")
        print("  - 结果、失败边界卡、模型反馈")
        print("  - 审计事件时间线")
        print("  - RAG 索引（向量 / BM25 / 切片元数据）")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def ensure_db_schema() -> None:
    """确保表结构存在。"""
    Base.metadata.create_all(bind=engine)


def reseed_via_api(base_url: str, api_key: str) -> None:
    """通过 /v1 API 重新注入演示场景（走真实飞书集成链路）。"""
    from scripts.mock_feishu_push import push_demo_scenarios
    push_demo_scenarios(base_url, api_key)


def reseed_direct() -> None:
    """直接写库方式 seed（不需要后端运行，兼容旧方式）。"""
    from scripts.seed_demo import (
        DEMO_USERS,
        ensure_experiment,
        ensure_experiment_2,
        ensure_project,
        ensure_user,
        seed_demo_data,
        seed_demo_data_exp2,
    )

    db = SessionLocal()
    try:
        users = {u: ensure_user(db, u, d, r) for u, d, r in DEMO_USERS}
        proj = ensure_project(db, users["pi"])
        members = [
            (users["pi"], "pi"),
            (users["lead"], "lead"),
            (users["executor"], "executor"),
        ]
        exp = ensure_experiment(db, proj, owner=users["lead"], members=members)
        exp2 = ensure_experiment_2(db, proj, owner=users["lead"], members=members)
        seed_demo_data(db, users, exp)
        seed_demo_data_exp2(db, users, exp2)
        db.commit()

        # 直接写库绕过了 /v1 接口，需手动重建 RAG 索引，否则 QA 读取过期/缺失索引
        try:
            from app.db import vec
            from app.config import settings
            from app.services.indexer import reindex_all
            vec.ensure_vec_tables(db, settings.QWEN_EMBEDDING_DIM)
            stats = reindex_all(db)
            db.commit()
            print(f"✓ RAG 索引已重建：claims={stats['claims']} results={stats['results']} "
                  f"evidence={stats['evidence']} boundaries={stats['boundaries']}")
        except Exception as e:
            print(f"⚠ RAG 索引重建失败（不阻断 seed）：{e}")

        print("✓ 直接 seed 演示数据完成（走数据库，非 /v1 接口）")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="重置演示数据")
    parser.add_argument(
        "--clear-only",
        action="store_true",
        help="只清除业务数据，不重新注入",
    )
    parser.add_argument(
        "--db-only",
        action="store_true",
        help="直接操作数据库（不走 /v1 API），不需要后端运行；使用 seed_demo.py 的完整链路数据",
    )
    parser.add_argument("--base-url", default="http://localhost:8081", help="后端服务地址（API 模式用）")
    parser.add_argument(
        "--api-key",
        default=None,
        help="PLATFORM_API_KEY（API 模式用，默认从 settings 读取）",
    )
    args = parser.parse_args()

    ensure_db_schema()

    if args.clear_only:
        clear_business_data()
        print("\n完成。业务数据已清除，基础数据（账号/项目/实验）保留。")
        return

    clear_business_data()
    print()

    if args.db_only:
        # 直接写库方式 —— 完整端到端场景（已确认、已阻断、已发布）
        reseed_direct()
    else:
        # 通过 /v1 API —— 模拟飞书推送，所有会议处于待复核状态
        from app.config import settings
        api_key = args.api_key or settings.PLATFORM_API_KEY
        try:
            reseed_via_api(args.base_url, api_key)
        except Exception as e:
            print(f"\n✗ 通过 API 注入失败：{e}", file=sys.stderr)
            print("提示：后端未启动？加上 --db-only 走直接写库方式。", file=sys.stderr)
            sys.exit(1)

    print("\n=== 重置完成 ===")


if __name__ == "__main__":
    main()
