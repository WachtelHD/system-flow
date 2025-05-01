# models.py
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData
from sqlalchemy.orm import foreign # Import foreign

# Convention for naming constraints for SQLite compatibility
metadata = MetaData(naming_convention={
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
})

db = SQLAlchemy(metadata=metadata)

# --- Models ---

class Step(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.String(255), nullable=True)
    estimated_time = db.Column(db.Integer, nullable=True) # In minutes
    icon = db.Column(db.String(50), nullable=True, default="➡️") # Placeholder icon
    tags = db.Column(db.String(200), nullable=True) # Comma-separated

    # Relationship: SystemItems pointing to this Step
    system_items = db.relationship('SystemItem',
                                   foreign_keys='SystemItem.item_id',
                                   primaryjoin="and_(SystemItem.item_type=='step', SystemItem.item_id==Step.id)",
                                   cascade="all, delete-orphan",
                                   lazy='dynamic',
                                   overlaps="system_items" # <--- ADDED OVERLAPS
                                  )

    # Relationship: Steps within Groups (handled by GroupStep)
    group_associations = db.relationship('GroupStep', back_populates='step', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Step {self.name}>'

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.String(255), nullable=True)
    icon = db.Column(db.String(50), nullable=True, default="📦") # Placeholder icon
    tags = db.Column(db.String(200), nullable=True) # Comma-separated

    # Relationship: Ordered steps within this group
    step_associations = db.relationship('GroupStep', back_populates='group',
                                        order_by='GroupStep.step_order',
                                        cascade="all, delete-orphan")

    # Relationship: SystemItems pointing to this Group
    system_items = db.relationship('SystemItem',
                                   foreign_keys='SystemItem.item_id',
                                   primaryjoin="and_(SystemItem.item_type=='group', SystemItem.item_id==Group.id)",
                                   cascade="all, delete-orphan",
                                   lazy='dynamic',
                                   overlaps="system_items" # <--- ADDED OVERLAPS
                                  )


    def get_total_time(self):
        """Calculates total estimated time for the group."""
        total = 0
        for assoc in self.step_associations:
            if assoc.step and assoc.step.estimated_time:
                total += assoc.step.estimated_time
        return total

    def __repr__(self):
        return f'<Group {self.name}>'

# Association object for Many-to-Many between Group and Step with order
class GroupStep(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    step_id = db.Column(db.Integer, db.ForeignKey('step.id'), nullable=False)
    step_order = db.Column(db.Integer, nullable=False) # Order of the step within the group

    group = db.relationship('Group', back_populates='step_associations')
    step = db.relationship('Step', back_populates='group_associations')

    __table_args__ = (db.UniqueConstraint('group_id', 'step_id', name='uq_group_step'),
                      db.UniqueConstraint('group_id', 'step_order', name='uq_group_order'))


# Represents an item (Step or Group) within a specific System flow
class SystemItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    system_name = db.Column(db.String(50), nullable=False) # 'Daily', 'Saturday', etc.
    item_type = db.Column(db.String(10), nullable=False) # 'step' or 'group'
    item_id = db.Column(db.Integer, nullable=False) # Refers to Step.id or Group.id
    item_order = db.Column(db.Integer, nullable=False) # Order within the system

    # Relationship to get the Step object (read-only)
    step = db.relationship('Step',
                           foreign_keys=[item_id],
                           primaryjoin="and_(SystemItem.item_type=='step', foreign(Step.id)==SystemItem.item_id)",
                           viewonly=True,
                           uselist=False)

    # Relationship to get the Group object (read-only)
    group = db.relationship('Group',
                            foreign_keys=[item_id],
                            primaryjoin="and_(SystemItem.item_type=='group', foreign(Group.id)==SystemItem.item_id)",
                            viewonly=True,
                            uselist=False)


    __table_args__ = (db.Index('ix_system_order', 'system_name', 'item_order'),
                      db.UniqueConstraint('system_name', 'item_order', name='uq_system_item_order'))

    def get_item_object(self):
        """Fetches the actual Step or Group object this item refers to."""
        if self.item_type == 'step':
            return self.step
        elif self.item_type == 'group':
            return self.group
        return None

    def get_item_name(self):
        item = self.get_item_object()
        return item.name if item else "Unknown Item"

    def get_item_icon(self):
        item = self.get_item_object()
        return item.icon if item else "❓"

    def get_item_time(self):
        item = self.get_item_object()
        if not item:
            return 0
        if self.item_type == 'step':
            return item.estimated_time or 0
        elif self.item_type == 'group':
            return item.get_total_time()
        return 0

    def __repr__(self):
        return f'<SystemItem {self.system_name} Order:{self.item_order} Type:{self.item_type} ID:{self.item_id}>'