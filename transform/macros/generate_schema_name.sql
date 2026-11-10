{# Use the folder schema as-is (staging, marts, reference) instead of dbt's default "analytics_staging". #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name if custom_schema_name else target.schema }}
{%- endmacro %}
