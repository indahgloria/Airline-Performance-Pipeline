{#
  BTS stores clock times as 'HHMM' text: '0545' = 5:45am, and '2400' = midnight.
  Convert to minutes after midnight (0-1439) so we can do math and bucket by hour.
#}
{% macro hhmm_to_minutes(col) -%}
    case
        when {{ col }} is null or {{ col }} !~ '^[0-9]{1,4}$' then null
        else ((({{ col }})::int / 100) % 24) * 60 + (({{ col }})::int % 100)
    end
{%- endmacro %}

{% macro to_num(col) -%}
    nullif({{ col }}, '')::numeric
{%- endmacro %}
