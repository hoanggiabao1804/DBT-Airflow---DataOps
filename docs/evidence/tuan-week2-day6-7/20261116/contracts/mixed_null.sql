select dateadd(hour, -1, sysutcdatetime()) as ModifiedDate union all select cast(null as datetime2(6))
