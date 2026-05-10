import './header.css';
import type { HeaderProps } from '../../types/header';

function Header({ day, time, guestsCount, onSaveSchedule }: HeaderProps) {
    
    return(
        <header className="header">
            <button className="save-schedule" onClick={onSaveSchedule}> СОХРАНИТЬ РАСПИСАНИЕ <i className="bi bi-download download-icon"></i> </button>

            <div className="guest-cnt">{guestsCount === null ? '' : `${guestsCount} чел.`}</div>

            <div className="icon-calendar">
                <i className="bi bi-calendar"></i>
                <div className="weakness">{day}</div>
            </div>

            <div className="time">{time}</div>

            <i className="bi bi-clock clock-icon"></i>
        </header>
    )
}

export default Header;