# app.py
import os
from flask import Flask, render_template, request, redirect, url_for, flash
from models import db, Step, Group, GroupStep, SystemItem

import click

# --- App Configuration ---
app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'systems.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-very-secret-key' # Change this for production!

db.init_app(app)

# --- Helper Functions ---
SYSTEM_NAMES = ['Daily', 'Saturday', 'Sunday', 'Weekly', 'Monthly']

def get_system_total_time(system_name):
    items = SystemItem.query.filter_by(system_name=system_name).all()
    total_time = 0
    for item in items:
        total_time += item.get_item_time()
    return total_time

# --- Routes ---

@app.route('/')
def dashboard():
    system_data = []
    for name in SYSTEM_NAMES:
        item_count = SystemItem.query.filter_by(system_name=name).count()
        total_time = get_system_total_time(name)
        system_data.append({
            'name': name,
            'item_count': item_count,
            'total_time': total_time
        })
    step_count = Step.query.count()
    group_count = Group.query.count()
    return render_template('dashboard.html',
                           systems=system_data,
                           step_count=step_count,
                           group_count=group_count,
                           system_names=SYSTEM_NAMES)

# --- Step Routes ---

@app.route('/steps', methods=['GET', 'POST'])
def steps_library():
    if request.method == 'POST':
        try:
            name = request.form['name']
            description = request.form.get('description')
            estimated_time = int(request.form['estimated_time']) if request.form.get('estimated_time') else None
            icon = request.form.get('icon') or '➡️'
            tags = request.form.get('tags')

            if not name:
                flash('Step name is required.', 'warning')
            elif Step.query.filter_by(name=name).first():
                 flash(f'Step "{name}" already exists.', 'warning')
            else:
                new_step = Step(name=name, description=description, estimated_time=estimated_time, icon=icon, tags=tags)
                db.session.add(new_step)
                db.session.commit()
                flash(f'Step "{name}" created successfully!', 'success')
                return redirect(url_for('steps_library')) # Redirect after POST
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating step: {e}', 'danger')

    all_steps = Step.query.order_by(Step.name).all()
    return render_template('steps.html', steps=all_steps, system_names=SYSTEM_NAMES)

@app.route('/steps/edit/<int:step_id>', methods=['POST'])
def edit_step(step_id):
    step = Step.query.get_or_404(step_id)
    try:
        original_name = step.name
        new_name = request.form['name']

        # Check if name changed and if new name already exists
        if new_name != original_name and Step.query.filter(Step.name == new_name, Step.id != step_id).first():
            flash(f'Step name "{new_name}" already exists.', 'warning')
            return redirect(url_for('steps_library'))

        step.name = new_name
        step.description = request.form.get('description')
        step.estimated_time = int(request.form['estimated_time']) if request.form.get('estimated_time') else None
        step.icon = request.form.get('icon') or '➡️'
        step.tags = request.form.get('tags')

        if not step.name:
            flash('Step name cannot be empty.', 'warning')
            db.session.rollback() # Don't commit empty name
        else:
            db.session.commit()
            flash(f'Step "{step.name}" updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating step: {e}', 'danger')

    return redirect(url_for('steps_library'))

@app.route('/steps/delete/<int:step_id>', methods=['POST'])
def delete_step(step_id):
    step = Step.query.get_or_404(step_id)
    try:
        step_name = step.name
        # Cascading deletes should handle GroupStep and SystemItem references
        db.session.delete(step)
        db.session.commit()
        flash(f'Step "{step_name}" deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting step: {e}. It might be in use.', 'danger') # More specific error handling needed in prod
    return redirect(url_for('steps_library'))

# --- Group Routes ---

@app.route('/groups', methods=['GET', 'POST'])
def groups_library():
    if request.method == 'POST':
        try:
            name = request.form['name']
            description = request.form.get('description')
            icon = request.form.get('icon') or '📦'
            tags = request.form.get('tags')

            if not name:
                flash('Group name is required.', 'warning')
            elif Group.query.filter_by(name=name).first():
                 flash(f'Group "{name}" already exists.', 'warning')
            else:
                new_group = Group(name=name, description=description, icon=icon, tags=tags)
                db.session.add(new_group)
                db.session.commit()
                flash(f'Group "{name}" created successfully! Add steps via Edit.', 'success')
                return redirect(url_for('groups_library')) # Redirect after POST
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating group: {e}', 'danger')

    all_groups = Group.query.order_by(Group.name).all()
    return render_template('groups.html', groups=all_groups, system_names=SYSTEM_NAMES)

@app.route('/groups/edit/<int:group_id>', methods=['GET', 'POST'])
def edit_group(group_id):
    group = Group.query.get_or_404(group_id)
    all_steps = Step.query.order_by(Step.name).all()

    if request.method == 'POST':
        try:
            # Update Group Details
            original_name = group.name
            new_name = request.form['name']

            if new_name != original_name and Group.query.filter(Group.name == new_name, Group.id != group_id).first():
                flash(f'Group name "{new_name}" already exists.', 'warning')
                return redirect(url_for('edit_group', group_id=group_id))

            group.name = new_name
            group.description = request.form.get('description')
            group.icon = request.form.get('icon') or '📦'
            group.tags = request.form.get('tags')

            if not group.name:
                flash('Group name cannot be empty.', 'warning')
                db.session.rollback()
                return redirect(url_for('edit_group', group_id=group_id))

            # Update Group Steps (handle order)
            ordered_step_ids = request.form.getlist('group_steps[]') # Get list of step IDs in order

            # Clear existing associations for this group
            GroupStep.query.filter_by(group_id=group_id).delete()

            # Add new associations based on the submitted order
            for index, step_id_str in enumerate(ordered_step_ids):
                step_id = int(step_id_str)
                if Step.query.get(step_id): # Ensure step exists
                    assoc = GroupStep(group_id=group_id, step_id=step_id, step_order=index)
                    db.session.add(assoc)

            db.session.commit()
            flash(f'Group "{group.name}" updated successfully!', 'success')
            return redirect(url_for('groups_library'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating group: {e}', 'danger')
            # Reload GET request data on error
            group = Group.query.get_or_404(group_id) # Re-fetch potential rolled back changes
            all_steps = Step.query.order_by(Step.name).all()


    # GET request or after POST error
    group_step_ids = {assoc.step_id for assoc in group.step_associations}
    return render_template('edit_group.html',
                           group=group,
                           all_steps=all_steps,
                           group_step_ids=group_step_ids,
                           system_names=SYSTEM_NAMES)


@app.route('/groups/delete/<int:group_id>', methods=['POST'])
def delete_group(group_id):
    group = Group.query.get_or_404(group_id)
    try:
        group_name = group.name
        # Cascading deletes should handle GroupStep and SystemItem references
        db.session.delete(group)
        db.session.commit()
        flash(f'Group "{group_name}" deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting group: {e}.', 'danger')
    return redirect(url_for('groups_library'))

# --- System Editor Routes ---

@app.route('/system/<string:system_name>', methods=['GET', 'POST'])
def system_editor(system_name):
    if system_name not in SYSTEM_NAMES:
        flash('Invalid system name.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        try:
            # Get the submitted order of items (e.g., "step-5", "group-2", "step-1")
            ordered_item_ids = request.form.getlist('system_items[]')

            # Clear existing items for this system
            SystemItem.query.filter_by(system_name=system_name).delete()

            # Add new items based on submitted order
            for index, item_identifier in enumerate(ordered_item_ids):
                item_type, item_id_str = item_identifier.split('-')
                item_id = int(item_id_str)

                # Basic validation: Check if the referenced Step or Group exists
                if item_type == 'step' and Step.query.get(item_id):
                     si = SystemItem(system_name=system_name, item_type=item_type, item_id=item_id, item_order=index)
                     db.session.add(si)
                elif item_type == 'group' and Group.query.get(item_id):
                     si = SystemItem(system_name=system_name, item_type=item_type, item_id=item_id, item_order=index)
                     db.session.add(si)
                else:
                    # Log or flash a warning about skipping an invalid item ID
                    print(f"Warning: Skipping invalid item '{item_identifier}' for system '{system_name}'")


            db.session.commit()
            flash(f'System "{system_name}" updated successfully!', 'success')
            return redirect(url_for('system_editor', system_name=system_name)) # Redirect to GET

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating system {system_name}: {e}', 'danger')
            # No need to redirect here, let GET request logic handle display

    # GET request
    system_items = SystemItem.query.filter_by(system_name=system_name).order_by(SystemItem.item_order).all()
    available_steps = Step.query.order_by(Step.name).all()
    available_groups = Group.query.order_by(Group.name).all()
    total_time = get_system_total_time(system_name)

    # Prepare items with their actual objects for the template
    detailed_system_items = []
    for item in system_items:
        obj = item.get_item_object()
        if obj: # Only add if the underlying step/group still exists
             detailed_system_items.append({
                 'system_item_id': item.id,
                 'type': item.item_type,
                 'id': item.item_id,
                 'name': obj.name,
                 'icon': obj.icon,
                 'time': item.get_item_time(),
                 'identifier': f"{item.item_type}-{item.item_id}" # For form submission value
             })


    return render_template('system_editor.html',
                           system_name=system_name,
                           system_items=detailed_system_items,
                           available_steps=available_steps,
                           available_groups=available_groups,
                           total_time=total_time,
                           system_names=SYSTEM_NAMES)

@app.cli.command("init-db")
def init_db_command():
    """Clear existing data and create new tables."""
    db.create_all()
    click.echo("Initialized the database.")

# --- Main Execution ---
if __name__ == '__main__':
    app.run(debug=True) # Enable debug mode for development

