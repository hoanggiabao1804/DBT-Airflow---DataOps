{% test line_total_matches(model, quantity_column, unit_price_column, discount_column, line_total_column, tolerance=0.01) %}

-- Decimal arithmetic preserves sub-cent differences at the tolerance boundary.
-- Missing inputs are left to separate not_null tests, not treated as zero.
select
    {{ adapter.quote(quantity_column) }},
    {{ adapter.quote(unit_price_column) }},
    {{ adapter.quote(discount_column) }},
    {{ adapter.quote(line_total_column) }}
from {{ model }}
where {{ adapter.quote(quantity_column) }} is not null
  and {{ adapter.quote(unit_price_column) }} is not null
  and {{ adapter.quote(discount_column) }} is not null
  and {{ adapter.quote(line_total_column) }} is not null
  and abs(
      cast({{ adapter.quote(line_total_column) }} as decimal(28, 8))
      - cast(
          cast({{ adapter.quote(quantity_column) }} as decimal(18, 6))
          * cast({{ adapter.quote(unit_price_column) }} as decimal(18, 6))
          * (cast(1 as decimal(9, 6)) - cast({{ adapter.quote(discount_column) }} as decimal(9, 6)))
          as decimal(28, 8)
      )
  ) > cast({{ tolerance }} as decimal(28, 8))

{% endtest %}
