import { useMemo } from 'react';
import './header.css';
import type { HeaderProps } from '../../types/header';
import { WEEKDAY_SHORT_RU } from '../../utils/scheduleFormat';

/** Мок посетителей по дню и строке часа (стабильно на слайде, выглядит «рандомно» по часам). */
function mockVisitorsCount(activeDay: number, time: string): number {
    const hourMatch = /^(\d{1,2})/.exec(time.trim());
    const hour = hourMatch ? Math.min(23, Math.max(0, parseInt(hourMatch[1], 10))) : 12;
    let h = 2_166_136_261;
    const seed = `${activeDay}|${hour}|${time}`;
    for (let i = 0; i < seed.length; i += 1) {
        h ^= seed.charCodeAt(i);
        h = Math.imul(h, 16_777_619);
    }
    return 52 + (Math.abs(h) % 229);
}

function Header({ activeDay, time, visitorsCount, onSelectDay }: HeaderProps) {
    const displayCount = useMemo(() => {
        if (visitorsCount !== undefined && Number.isFinite(visitorsCount) && visitorsCount > 0) {
            return visitorsCount;
        }
        return mockVisitorsCount(activeDay, time);
    }, [activeDay, time, visitorsCount]);

    const peopleLabel = displayCount > 0 ? `${displayCount} чел.` : '—';

    return (
        <header className="header">
            <div className="header__brand">
                <div className="header__logo-wrap">
                    <img
                        className="header__logo"
                        src="/vkusno-symbol.png"
                        alt="Вкусно — и точка"
                        width={72}
                        height={40}
                        decoding="async"
                    />
                </div>
            </div>

            <div className="header__center">
                <div className="header__clock">{time}</div>
                <nav className="header__week" aria-label="День недели">
                    {WEEKDAY_SHORT_RU.map((label, i) => {
                        const day = i + 1;
                        const isActive = day === activeDay;
                        return (
                            <button
                                key={label}
                                type="button"
                                className={`header__day-btn${isActive ? ' header__day-btn--active' : ''}`}
                                onClick={() => onSelectDay(day)}
                                aria-current={isActive ? 'true' : undefined}
                                aria-label={label}
                            >
                                {label}
                            </button>
                        );
                    })}
                </nav>
            </div>

            <div className="header__stat-pill" title="Ожидаемые посетители за час">
                <i className="bi bi-person-fill header__stat-icon" aria-hidden />
                <span className="header__stat-value">{peopleLabel}</span>
            </div>
        </header>
    );
}

export default Header;
