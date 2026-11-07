{% test positive_values(model, column_name, allow_zero=true) %}

-- NULL is checked separately with not_null when the column is required.
select {{ adapter.quote(column_name) }}
from {{ model }}
where {{ adapter.quote(column_name) }} is not null
  and {{ adapter.quote(column_name) }} {% if allow_zero %}< 0{% else %}<= 0{% endif %}

{% endtest %}
