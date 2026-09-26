"""Admin-only resource metadata and case sharing. No model calls."""
import uuid
from fastapi import APIRouter, Depends
from ..auth import require_admin
from .. import enablement as service
from .. import resource_categories as categories

router = APIRouter(tags=['enablement-admin'], dependencies=[Depends(require_admin)])

@router.get('/admin/enablement/resource-categories')
def list_categories():
    return categories.listing()

@router.post('/admin/enablement/resource-categories', status_code=201)
def add_category(payload: categories.CategoryCreate):
    return categories.save(payload)

@router.patch('/admin/enablement/resource-categories/{category_id}')
def edit_category(category_id: str, payload: categories.CategoryEdit):
    return categories.save(payload, category_id)

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

# Typed route factories keep the two lifecycles identical without a second permission system.
def register_actions(prefix: str, kind: service.Kind):
    def set_permissions(source_id: str, payload: service.Permissions, user=Depends(require_admin)):
        return service.permissions(kind,source_id,payload,user['id'])
    def publish(source_id: str, payload: service.Revision, user=Depends(require_admin)):
        return service.publish(kind,source_id,payload,user['id'])
    def unpublish(source_id: str, payload: service.Unpublish, user=Depends(require_admin)):
        return service.unpublish(kind,source_id,payload,user['id'])
    for suffix, endpoint, method in [('permissions',set_permissions,'PATCH'),('publish',publish,'POST'),('unpublish',unpublish,'POST')]:
        router.add_api_route(prefix+'/'+suffix,endpoint,methods=[method],name=kind+'_'+suffix)

register_actions('/admin/enablement/resources/{source_id}', 'resource')
