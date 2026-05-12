import './header.css';
import type { HeaderProps } from '../../types/header';
import { WEEKDAY_SHORT_RU } from '../../utils/scheduleFormat';

function Header({ activeDay, time, visitorsCount, onSelectDay }: HeaderProps) {
    const peopleLabel = Number.isFinite(visitorsCount) && visitorsCount > 0 ? `${visitorsCount} чел.` : '—';

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
