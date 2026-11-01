{# Concatenate every digit in a string into a number: '6-8' -> 68, '1st Floor 45 Main St' -> 145.
   No digits (or NULL) -> NULL. #}
{% macro digits_to_number(column) -%}
    try_cast(nullif(regexp_replace({{ column }}, '[^0-9]', '', 'g'), '') as hugeint)
{%- endmacro %}
