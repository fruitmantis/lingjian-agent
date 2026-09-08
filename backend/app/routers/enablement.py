"""Admin-only resource metadata and case sharing. No model calls."""
import uuid
from fastapi import APIRouter, Depends
from ..auth import require_admin
from .. import enablement as service

router = APIRouter(tags=['enablement-admin'], dependencies=[Depends(require_admin)])

@router.get('/admin/enablement/resources')
def list_resources():
    return service.listing()

@router.post('/admin/enablement/resources', status_code=201)
def create_resource(payload: service.ResourceSave, user=Depends(require_admin)):
    return service.save('resource',str(uuid.uuid4()),payload,user['id'])

@router.get('/admin/enablement/resources/{source_id}')
def get_resource(source_id: str):
    return service.detail('resource',source_id)

@router.put('/admin/enablement/resources/{source_id}')
def edit_resource(source_id: str, payload: service.ResourceSave, user=Depends(require_admin)):
    service.detail('resource',source_id)
    return service.save('resource',source_id,payload,user['id'])

@router.get('/admin/cases/{source_id}/sharing')
def get_sharing(source_id: str):
    return service.detail('case',source_id)

@router.put('/admin/cases/{source_id}/sharing')
def save_sharing(source_id: str, payload: service.ShareSave, user=Depends(require_admin)):
    return service.save('case',source_id,payload,user['id'])

# Typed route factories keep the two lifecycles identical without a second permission system.
def register_actions(prefix: str, kind: service.Kind):
    def set_permissions(source_id: str, payload: service.Permissions, user=Depends(require_admin)):
        return service.permissions(kind,source_id,payload,user['id'])
    def record_review(source_id: str, payload: service.Review, user=Depends(require_admin)):
        return service.review(kind,source_id,payload,user['id'])
    def publish(source_id: str, payload: service.Revision, user=Depends(require_admin)):
        return service.publish(kind,source_id,payload,user['id'])
    def unpublish(source_id: str, payload: service.Unpublish, user=Depends(require_admin)):
        return service.unpublish(kind,source_id,payload,user['id'])
    for suffix, endpoint, method in [('permissions',set_permissions,'PATCH'),('review',record_review,'POST'),('publish',publish,'POST'),('unpublish',unpublish,'POST')]:
        router.add_api_route(prefix+'/'+suffix,endpoint,methods=[method],name=kind+'_'+suffix)

register_actions('/admin/enablement/resources/{source_id}', 'resource')
register_actions('/admin/cases/{source_id}/sharing', 'case')
