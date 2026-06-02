"""Aggregate API v1 routes."""

from fastapi import APIRouter

from backend.api.routes import health, papers, patrol

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(papers.router, tags=["papers"])
api_router.include_router(patrol.router, tags=["patrol"])
