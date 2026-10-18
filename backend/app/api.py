"""API route handlers for PatchLoom."""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from app.analysis import analyze_repository
from app.config import settings
from app.github_client import (
    GitHubUpstreamError,
    InvalidGitHubURLError,
    IssueClosedError,
    IssueNotFoundError,
    RateLimitExceededError,
    RepoAccessError,
    RepoNotFoundError,
)
from app.planner import generate_first_pr_plan
from app.rate_limit import rate_limit
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    HealthResponse,
    PlanRequest,
    PlanResponse,
)

router = APIRouter(prefix="/api")


@router.get(
    "/health",
    response_model=HealthResponse,
    dependencies=[Depends(rate_limit("health", lambda: settings.HEALTH_RATE_LIMIT))],
)
async def health_check() -> HealthResponse:
    """Safe health check endpoint reporting service readiness without secrets."""
    return HealthResponse(
        status="ok",
        demo_mode=settings.DEMO_MODE,
        environment=settings.APP_ENV,
        has_gemini_key=settings.has_gemini_key,
        has_github_token=settings.has_github_token,
    )


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    dependencies=[Depends(rate_limit("analyze", lambda: settings.ANALYZE_RATE_LIMIT))],
)
async def analyze_repo_endpoint(request: AnalyzeRequest) -> AnalyzeResponse:
    """Analyze a public GitHub repository and produce ranked candidate issues."""
    try:
        return await analyze_repository(
            repo_url=request.repo_url,
            profile=request.profile,
            provider_name=request.provider,
            demo=request.demo or False,
        )
    except InvalidGitHubURLError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RepoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except RepoAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except GitHubUpstreamError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub API upstream service error. Please try again later.",
        ) from exc
    except Exception as exc:
        request_id = str(uuid.uuid4())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected internal error occurred (Request ID: {request_id})",
        ) from exc


@router.post(
    "/plan",
    response_model=PlanResponse,
    dependencies=[Depends(rate_limit("plan", lambda: settings.PLAN_RATE_LIMIT))],
)
async def generate_plan_endpoint(request: PlanRequest) -> PlanResponse:
    """Generate a bounded first-PR plan for a selected open GitHub issue."""
    try:
        return await generate_first_pr_plan(
            repo_url=request.repo_url,
            issue_number=request.issue_number,
            profile=request.profile,
            provider_name=request.provider,
            demo=request.demo or False,
        )
    except InvalidGitHubURLError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except IssueClosedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except (RepoNotFoundError, IssueNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except RepoAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except GitHubUpstreamError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub API upstream service error. Please try again later.",
        ) from exc
    except Exception as exc:
        request_id = str(uuid.uuid4())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected internal error occurred (Request ID: {request_id})",
        ) from exc

