import { useEffect, useState } from 'react';
import type { AnimationScheduleItem } from '../../types/schedule';
import WalkingPerson from '../WalkingPerson/WalkingPerson';
import { staffingTone, type StaffingTone } from '../../utils/staffingTone';
import './week-stations-board.css';

type WeekStationsBoardProps = {
    items: AnimationScheduleItem[];
};

type ZoneDef = {
    codes: string[];
    label: string;
    icon: string;
    variant: 'kitchen' | 'fries' | 'drinks' | 'counter' | 'hall';
    wide?: boolean;
    shirt: string;
};

const ZONES: ZoneDef[] = [
    { codes: ['K'], label: 'Кухня', icon: 'bi-fire', variant: 'kitchen', shirt: '#ff8f5c' },
    { codes: ['FF'], label: 'Картофель', icon: 'bi-basket2-fill', variant: 'fries', shirt: '#ffd84d' },
    { codes: ['BVR'], label: 'Напитки', icon: 'bi-droplet', variant: 'drinks', shirt: '#6eb8ff' },
    { codes: ['C'], label: 'Прилавок', icon: 'bi-cash-stack', variant: 'counter', shirt: '#ff8fb8' },
    { codes: ['TS'], label: 'Зал', icon: 'bi-people-fill', variant: 'hall', wide: true, shirt: '#7dde9f' },
];

/** Строка из API похожа на id сотрудника, а не на отображаемое имя */
function isTechnicalStaffId(raw: string): boolean {
    const s = raw.trim();
    if (!s) return false;
    if (/\d/.test(s)) return true;
    if (/^[A-Za-z]{1,8}[-_/][A-Za-z0-9_-]+$/i.test(s)) return true;
    if (/^[0-9a-f-]{32,36}$/i.test(s)) return true;
    return false;
}

/** Только id над человечком; «имена» не показываем — подставляем код станции + номер */
function staffIdLabel(raw: string | undefined, stationKey: string, index: number): { text: string; title?: string } {
    const s = raw?.trim() ?? '';
    if (!s) {
        return { text: `${stationKey}-${index + 1}` };
    }
    if (isTechnicalStaffId(s)) {
        return { text: s };
    }
    return {
        text: `${stationKey}-${String(index + 1).padStart(2, '0')}`,
        title: s,
    };
}

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

function findItemForZone(items: AnimationScheduleItem[], codes: string[]): AnimationScheduleItem | undefined {
    const upper = codes.map((c) => c.toUpperCase());
    return items.find((row) => upper.includes(row.station.trim().toUpperCase()));
}

function progressPercent(actual: number, expected: number): number {
    if (expected <= 0) {
        return actual > 0 ? 100 : 0;
    }
    return Math.min(100, Math.round((actual / expected) * 100));
}

function WeekStationsBoard({ items }: WeekStationsBoardProps) {
    const [sceneTimeMs, setSceneTimeMs] = useState(0);

    useEffect(() => {
        const startedAt = Date.now();
        const timer = window.setInterval(() => {
            setSceneTimeMs(Date.now() - startedAt);
        }, 120);
        return () => window.clearInterval(timer);
    }, []);

    if (items.length === 0) {
        return (
            <div className="week-stations-board week-stations-board--empty">
                <p className="week-stations-board__empty">Нет данных по станциям за этот час.</p>
            </div>
        );
    }

    return (
        <div className="week-stations-board">
            <div className="week-stations-board__grid">
                {ZONES.map((zone) => {
                    const item = findItemForZone(items, zone.codes);
                    const actual = item ? actualCount(item) : 0;
                    const expected = item ? Math.max(0, item.expectedPeopleCount) : 0;
                    const tone = item ? staffingTone(expected, actual, item.expectationIndicator) : 'ok';
                    const pct = item ? progressPercent(actual, expected) : 0;
                    const ids = item?.employeeIds ?? [];
                    const peopleCount = ids.length > 0 ? ids.length : actual;
                    const walkCount = Math.min(Math.max(peopleCount, 0), 8);
                    const arenaW = zone.wide ? 280 : 152;
                    const shirt = zone.shirt;
                    const stationKey = zone.codes[0]?.toUpperCase() ?? 'X';

                    return (
                        <article
                            key={zone.variant}
                            className={`zone-card zone-card--${zone.variant}${zone.wide ? ' zone-card--wide' : ''}`}
                        >
                            <div className="zone-card__head">
                                <i className={`bi ${zone.icon} zone-card__head-icon`} aria-hidden />
                                <h2 className="zone-card__title">{zone.label}</h2>
                            </div>

                            {walkCount > 0 ? (
                                <div className={`zone-card__walk-layer${zone.wide ? ' zone-card__walk-layer--wide' : ''}`} aria-hidden>
                                    {Array.from({ length: walkCount }).map((_, idx) => {
                                        const cycle = 5200;
                                        const phase = sceneTimeMs % cycle;
                                        const offset = idx * 260;
                                        const cols = Math.min(zone.wide ? 6 : 4, Math.max(1, walkCount));
                                        const col = idx % cols;
                                        const span = Math.max(1, cols - 1);
                                        const targetX = 22 + (col / span) * (arenaW - 44);
                                        const targetY = 80;
                                        const lane = idx % 2;
                                        const fromX = -52 - (idx % 3) * 10;
                                        const fromY = 78 + lane * 6;
                                        const exitX = arenaW + 44;
                                        const exitY = 80 + lane * 5;
                                        const idLabel = staffIdLabel(ids[idx], stationKey, idx);
                                        return (
                                            <WalkingPerson
                                                key={`walk-${zone.variant}-${idLabel.text}-${idx}`}
                                                label={idLabel.text}
                                                labelTitle={idLabel.title}
                                                shirtColor={shirt}
                                                sceneTimeMs={phase}
                                                arrivalTimeMs={650 + offset}
                                                departureTimeMs={3600 + offset}
                                                walkDurationMs={680}
                                                targetX={targetX}
                                                targetY={targetY}
                                                fromX={fromX}
                                                fromY={fromY}
                                                exitX={exitX}
                                                exitY={exitY}
                                            />
                                        );
                                    })}
                                </div>
                            ) : (
                                <div className="zone-card__walk-placeholder">
                                    <span className="zone-card__vacant">Никого</span>
                                </div>
                            )}

                            <div className="zone-card__meta">
                                {item ? (
                                    <>
                                        <span className={`zone-card__tone zone-card__tone--${tone}`}>{toneLabel(tone)}</span>
                                        <span className="zone-card__ratio">
                                            {actual}/{expected} чел
                                        </span>
                                    </>
                                ) : (
                                    <span className="zone-card__vacant">Нет слота в данных</span>
                                )}
                            </div>

                            <div className="zone-card__bar-wrap" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
                                <div className="zone-card__bar-fill" style={{ width: `${pct}%` }} />
                            </div>
                        </article>
                    );
                })}
            </div>
        </div>
    );
}

export default WeekStationsBoard;
