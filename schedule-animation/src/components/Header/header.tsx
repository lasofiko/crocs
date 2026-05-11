import './header.css';
import type { HeaderProps } from '../../types/header';

function Header({
    day,
    time,
    onSaveSchedule,
    screenDimmed = false,
}: HeaderProps) {
    return (
        <header className="header">
            <div className="header__chrome header__chrome--left">
                <button type="button" className="save-schedule" onClick={onSaveSchedule}>
                    СОХРАНИТЬ РАСПИСАНИЕ <i className="bi bi-download download-icon" />
                </button>
            </div>

            <div className="header__time-rail">
                <div
                    className={`header__clock-dial ${screenDimmed ? 'header__clock-dial--night' : ''}`}
                    aria-hidden
                >
                    <div className="header__mini-clock">
                        <div className="header__mini-clock-hand" />
                    </div>
                </div>
                <div className="time">{time}</div>
            </div>

            <div className="header__chrome header__chrome--right">
                <div className="icon-calendar">
                    <i className="bi bi-calendar" />
                    <div className="weakness">{day}</div>
                </div>
            </div>

            {screenDimmed ? <div className="header__screen-dim" aria-hidden /> : null}
        </header>
    );
}

export default Header;
