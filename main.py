from pathlib import Path

import yaml


def define_env(env: object) -> None:
    """This is the hook for defining variables, macros and filters."""

    @env.macro
    def render_config_options():
        with open(
            Path(env.project_dir) / "ckanext" / "tables" / "config_declaration.yml"
        ) as f:
            data = yaml.safe_load(f)

        markdown = ""

        for group in data.get("groups", []):
            section_name = group.get("annotation", "General Settings")
            section_desc = group.get("description", "").strip()
            options = group.get("options", [])

            markdown += f"## {section_name}\n\n"

            if section_desc:
                markdown += f"{section_desc}\n\n"

            markdown += "---\n\n"

            for opt in options:
                markdown += _generate_option_markdown(opt)

        return markdown

    def _generate_option_markdown(opt: dict) -> str:
        markdown = ""

        key = opt.get("key", "")
        default = opt.get("default", "None")
        example = opt.get("example", "")
        desc = opt.get("description", "").strip()
        dtype = opt.get("type", "string")
        allowed_values = opt.get("allowed_values", [])

        markdown += f"### `{key}`\n\n"

        if desc:
            markdown += f"{desc}\n\n"

        markdown += "| | |\n"
        markdown += "|---|---|\n"
        markdown += f"| **Type** | `{dtype}` |\n"
        markdown += f"| **Default** | `{default}` |\n"

        if allowed_values:
            values_str = ", ".join(f"`{v}`" for v in allowed_values)
            markdown += f"| **Allowed values** | {values_str} |\n"

        markdown += "\n"

        if example:
            markdown += f"```ini\n{key} = {example}\n```\n\n"

        markdown += "---\n\n"

        return markdown
