{# Use the layer's schema name as-is (staging, warehouse, ...) instead of dbt's <target>_<schema>. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ (custom_schema_name or target.schema) | trim }}
{%- endmacro %}
