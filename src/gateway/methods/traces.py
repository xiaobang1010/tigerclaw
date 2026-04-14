from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from services.trace.store import get_trace_store

router = APIRouter(tags=["traces"])


@router.get("/traces")
async def list_traces(
    request: Request,
    session_id: str | None = None,
    model: str | None = None,
    status: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """查询行为轨迹列表。"""
    store = get_trace_store()
    traces = store.list_traces(
        session_id=session_id,
        model=model,
        status=status,
        start_time=start_time,
        end_time=end_time,
        limit=min(limit, 200),
        offset=offset,
    )
    return {
        "traces": [t.to_dict() for t in traces],
        "count": len(traces),
        "limit": limit,
        "offset": offset,
    }


@router.get("/traces/stats")
async def get_trace_stats(request: Request):
    """获取轨迹统计信息。"""
    store = get_trace_store()
    return store.get_stats()


@router.get("/traces/{trace_id}")
async def get_trace_detail(request: Request, trace_id: str):
    """获取轨迹详情。"""
    store = get_trace_store()
    trace = store.get(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="轨迹不存在")
    return trace.to_dict()
