{% test no_future_dates(model, column_name) %}

-- Compare timestamps, including the time of day. NULL uses a separate not_null.
select {{ adapter.quote(column_name) }}
from {{ model }}
where {{ adapter.quote(column_name) }} is not null
  and {{ adapter.quote(column_name) }} > getutcdate()

{% endtest %}
