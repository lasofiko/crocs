import type { AnimationScheduleItem } from '../../types/schedule';
import { staffingTone, type StaffingTone } from '../../utils/staffingTone';
import './week-stations-board.css';

type WeekStationsBoardProps = {
    items: AnimationScheduleItem[];
};

function actualCount(item: AnimationScheduleItem): number {
    if (item.atStationCount !== undefined && Number.isFinite(item.atStationCount)) {
        return item.atStationCount;
    }

    return item.employeeIds.length;
}

function toneLabel(tone: StaffingTone): string {
    if (tone === 'ok') return 'Норма';
    if (tone === 'warn') return 'Ниже нормы';
    return 'Критично';
}

function WeekStationsBoard({ items }: WeekStationsBoardProps) {
    if (items.length === 0) {
        return (
            <div className="week-stations-board week-stations-board--empty">
                <p className="week-stations-board__empty">Нет данных по станциям за этот час.</p>
            </div>
        );
    }

    return (
        <div className="week-stations-board">
            <ul className="week-stations-board__grid">
                {items.map((item) => {
                    const actual = actualCount(item);
                    const expected = Math.max(0, item.expectedPeopleCount);
                    const tone = staffingTone(expected, actual, item.expectationIndicator);

                    return (
                        <li key={`${item.day}-${item.hour}-${item.station}`} className={`week-stations-card week-stations-card--${tone}`}>
                            <div className="week-stations-card__title">{item.station}</div>
                            <div className="week-stations-card__counts">
                                <span className="week-stations-card__actual">{actual}</span>
                                <span className="week-stations-card__sep">/</span>
                                <span className="week-stations-card__expected">{expected}</span>
                                <span className="week-stations-card__hint"> чел.</span>
                            </div>
                            <div className={`week-stations-card__badge week-stations-card__badge--${tone}`}>{toneLabel(tone)}</div>
                            {item.employeeIds.length > 0 ? (
                                <div className="week-stations-card__ids" title={item.employeeIds.join(', ')}>
                                    {item.employeeIds.slice(0, 6).join(', ')}
                                    {item.employeeIds.length > 6 ? '…' : ''}
                                </div>
                            ) : null}
                        </li>
                    );
                })}
            </ul>
        </div>
    );
}

export default WeekStationsBoard;
