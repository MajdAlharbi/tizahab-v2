from django.db import migrations


def create_role(apps, schema_editor):
    alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    User = apps.get_model("auth", "User")
    group, _ = Group.objects.using(alias).get_or_create(name="Content Manager")
    for model, actions in {
        "event": ("view", "add", "change"),
        "sourcerecord": ("view", "change"),
        "catalogsource": ("view",),
        "syncrun": ("view",),
        "contentauditlog": ("view",),
    }.items():
        content_type, _ = ContentType.objects.using(alias).get_or_create(
            app_label="events", model=model
        )
        for action in actions:
            permission, _ = Permission.objects.using(alias).get_or_create(
                content_type_id=content_type.pk,
                codename=f"{action}_{model}",
                defaults={"name": f"Can {action} {model}"},
            )
            group.permissions.add(permission)
    for user in User.objects.using(alias).filter(is_staff=True, is_superuser=False):
        user.groups.add(group)


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0020_catalog_sources"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]
    operations = [migrations.RunPython(create_role, migrations.RunPython.noop)]
