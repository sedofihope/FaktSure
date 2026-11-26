from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.core.permissions import require_roles
from app.db.session import get_db
from app.models.client import Client
from app.models.user import User
from app.schemas.client import ClientCreate, ClientResponse, ClientUpdate

router = APIRouter(prefix="/clients", tags=["clients"])

@router.get("", response_model=list[ClientResponse])
def list_clients(db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN", "ACCOUNTANT", "VALIDATOR"))):
    return list(db.scalars(select(Client).order_by(Client.id)))

@router.post("", response_model=ClientResponse, status_code=201)
def create_client(payload: ClientCreate, db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN"))):
    client = Client(**payload.model_dump())
    db.add(client); db.commit(); db.refresh(client)
    return client

@router.get("/{client_id}", response_model=ClientResponse)
def get_client(client_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN", "ACCOUNTANT", "VALIDATOR"))):
    client = db.scalar(select(Client).where(Client.public_id == client_id))
    if client is None:
        raise NotFoundError("Client not found")
    return client

@router.put("/{client_id}", response_model=ClientResponse)
def update_client(client_id: UUID, payload: ClientUpdate, db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN"))):
    client = db.scalar(select(Client).where(Client.public_id == client_id))
    if client is None:
        raise NotFoundError("Client not found")
    for name, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, name, value)
    db.commit(); db.refresh(client)
    return client

@router.delete("/{client_id}", status_code=204)
def delete_client(client_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN"))):
    client = db.scalar(select(Client).where(Client.public_id == client_id))
    if client is None:
        raise NotFoundError("Client not found")
    client.is_active = False
    db.commit()
