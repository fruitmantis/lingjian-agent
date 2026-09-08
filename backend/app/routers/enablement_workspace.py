"""Workspace resource and source-context endpoints. No plan or model operations."""
from typing import Literal
from fastapi import APIRouter, Depends, Query, Response
from pydantic import Field
from ..auth import require_active_user
from ..database import get_db
from ..enablement import StrictModel
from .. import enablement_catalog as catalog


def no_store(response: Response):
    response.headers['Cache-Control']='no-store'


router=APIRouter(prefix='/enablement',tags=['enablement-workspace'],dependencies=[Depends(require_active_user),Depends(no_store)])
SourceType=Literal['course','lab','case']


@router.get('/resources')
def resources(source_type: SourceType | None=None,q: str | None=Query(None,max_length=200),
              capability_tag_id: str | None=None,contributor_id: str | None=None,
              status: Literal['published','unpublished']='published',
              audience: str | None=None,product_direction: str | None=None,difficulty: str | None=None,
              language: str | None=None,site: str | None=None,cost: str | None=None,
              account_requirement: str | None=None,environment_requirement: str | None=None,prerequisites: str | None=None,
              page: int=Query(1,ge=1),page_size: int=Query(12,ge=1,le=50)):
    return catalog.catalog(**locals())


@router.get('/resource-filters')
def filters():
    return catalog.filter_options()


@router.get('/resources/{source_type}/{source_id}')
def detail(source_type: SourceType,source_id: str,source_version: int | None=Query(None,ge=1)):
    with get_db() as conn:
        conn.execute('BEGIN')
        return catalog.public_detail(conn,source_type,source_id,source_version)


class RedirectRequest(StrictModel):
    source_version: int=Field(ge=1)


@router.post('/resources/{source_type}/{source_id}/redirect')
def redirect(source_type: SourceType,source_id: str,payload: RedirectRequest,user=Depends(require_active_user)):
    return catalog.redirect(source_type,source_id,payload.source_version,user['id'])


@router.get('/context')
def context(partner_id: str | None=None,task_id: str | None=None,case_id: str | None=None,
            case_version: int | None=Query(None,ge=1),user=Depends(require_active_user)):
    return catalog.context(user,partner_id,task_id,case_id,case_version)
