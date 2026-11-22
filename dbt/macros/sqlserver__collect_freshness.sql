{% macro sqlserver__collect_freshness(source, loaded_at_field, filter) %}
    {# The adapter's inherited current_timestamp uses server-local SYSDATETIME.
       Source timestamps in this project are interpreted as UTC. Scope the UTC
       clock to freshness, without changing timestamps in other dbt operations. #}
    {% set warn_hours = var('source_freshness_warn_hours', 24) | int %}
    {% set error_hours = var('source_freshness_error_hours', 48) | int %}
    {% if warn_hours <= 0 or error_hours <= warn_hours %}
        {{ exceptions.raise_compiler_error('Freshness hours must satisfy 0 < warn < error.') }}
    {% endif %}
    {% call statement('collect_freshness', fetch_result=True, auto_begin=False) %}
        select
            max({{ loaded_at_field }}) as max_loaded_at,
            cast(sysutcdatetime() as datetime2(6)) as snapshotted_at
        from {{ source }}
        {% if filter %}
            where {{ filter }}
        {% endif %}
    {% endcall %}
    {{ return(load_result('collect_freshness')) }}
{% endmacro %}
