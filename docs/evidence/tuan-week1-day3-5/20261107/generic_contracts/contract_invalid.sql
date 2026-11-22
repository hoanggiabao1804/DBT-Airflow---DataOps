select *
from (values
    (cast(1 as int), cast(-0.000001 as decimal(18, 6)), cast(-0.000001 as decimal(18, 6)), cast(dateadd(minute, 5, getutcdate()) as datetime2(7)), cast(3 as decimal(18, 6)), cast(10 as decimal(18, 6)), cast(0.1 as decimal(9, 6)), cast(27.010001 as decimal(28, 8))),
    (cast(2 as int), cast(-1 as decimal(18, 6)), cast(-1 as decimal(18, 6)), cast(dateadd(day, 1, getutcdate()) as datetime2(7)), cast(3 as decimal(18, 6)), cast(10 as decimal(18, 6)), cast(0.1 as decimal(9, 6)), cast(26.989999 as decimal(28, 8))),
    (cast(3 as int), cast(0 as decimal(18, 6)), cast(0 as decimal(18, 6)), cast(dateadd(day, -1, getutcdate()) as datetime2(7)), cast(3 as decimal(18, 6)), cast(10 as decimal(18, 6)), cast(0.1 as decimal(9, 6)), cast(99 as decimal(28, 8))),
    (cast(4 as int), cast(1 as decimal(18, 6)), cast(1 as decimal(18, 6)), cast(getutcdate() as datetime2(7)), cast(3 as decimal(18, 6)), cast(10 as decimal(18, 6)), cast(0.1 as decimal(9, 6)), cast(27 as decimal(28, 8))),
    (cast(5 as int), cast(null as decimal(18, 6)), cast(null as decimal(18, 6)), cast(null as datetime2(7)), cast(null as decimal(18, 6)), cast(10 as decimal(18, 6)), cast(0 as decimal(9, 6)), cast(999 as decimal(28, 8)))
) as fixture ([case id], [amount allowed], [amount strict], [occurred at], [quantity], [unit price], [discount rate], [line total])
