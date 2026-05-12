import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import './animation.css';
import { DEFAULT_PAGE_SIZE, attachPublicStaffingRequirements, fetchScheduleAnimationPage, fetchScheduleExcel, fetchPublicScheduleXlsxBlob, tryLoadScheduleFromPublicXlsx } from '../../api/scheduleApi';
import Header from '../../components/Header/header';
import PlaybackBar, { type PlaybackSpeed } from '../../components/PlaybackBar/PlaybackBar';
import WeekStationsBoard from '../../components/WeekStationsBoard/WeekStationsBoard';
import { MOCK_SCHEDULE_ANIMATION_ROWS } from '../../data/mockScheduleAnimation';
import type { AnimationScheduleItem } from '../../types/schedule';
import { buildWeekSlidesFromSchedule, type WeekHourSlide } from '../../utils/buildWeekSlides';
import { dedupeScheduleRows } from '../../utils/dedupeScheduleRows';
import { filterValidScheduleRows } from '../../utils/filterValidScheduleRows';
import { formatHour } from '../../utils/scheduleFormat';

/** Рабочие часы: дольше на слайд; ночь 0–6 — быстро «проматываем» до открытия */
const WORKING_SLIDE_MS = 5000;
const OFF_HOURS_SLIDE_MS = 180;
const WORK_START_HOUR = 7;
const WORK_END_HOUR = 23;

/** Длительность анимации «переворот таблички → исчезновение» при открытии (см. animation.css) */
const DOOR_SIGN_OPEN_MS = 1200;

function isWorkingHour(hour: number): boolean {
    return hour >= WORK_START_HOUR && hour <= WORK_END_HOUR;
}

function visitorsForSlide(items: AnimationScheduleItem[]): number {
    let best = 0;
    for (const row of items) {
        const v = row.visitorsCount;
        if (v !== undefined && Number.isFinite(v) && v > best) {
            best = v;
        }
    }
    return best;
}

function findSlideIndexForDay(slides: WeekHourSlide[], targetDay: number, preferredHour: number): number {
    const sameHour = slides.findIndex((s) => s.day === targetDay && s.hour === preferredHour);
    if (sameHour >= 0) {
        return sameHour;
    }
    const any = slides.findIndex((s) => s.day === targetDay);
    return any >= 0 ? any : 0;
}

function Animation() {
    const [scheduleData, setScheduleData] = useState<AnimationScheduleItem[]>(() => [...MOCK_SCHEDULE_ANIMATION_ROWS]);
    const [currentIndex, setCurrentIndex] = useState(0);
    const [isPaused, setIsPaused] = useState(false);
    const [fetchHint, setFetchHint] = useState<string | null>(null);
    const [playbackSpeed, setPlaybackSpeed] = useState<PlaybackSpeed>(1);

    const slides = useMemo(() => buildWeekSlidesFromSchedule(scheduleData), [scheduleData]);

    const currentSlide = slides[currentIndex] ?? slides[0];
    const isWorkingTime = currentSlide !== undefined && isWorkingHour(currentSlide.hour);

    const slideCount = slides.length;

    const [doorAnim, setDoorAnim] = useState<'off' | 'closed' | 'opening'>(() => {
        const s = slides[0];
        return s !== undefined && isWorkingHour(s.hour) ? 'off' : 'closed';
    });
    const prevWorkingRef = useRef<boolean | undefined>(undefined);

    useLayoutEffect(() => {
        if (prevWorkingRef.current === undefined) {
            prevWorkingRef.current = isWorkingTime;
            return;
        }
        if (prevWorkingRef.current === isWorkingTime) {
            return;
        }

        const wasWorking = prevWorkingRef.current;
        prevWorkingRef.current = isWorkingTime;

        if (!isWorkingTime) {
            setDoorAnim('closed');
            return;
        }
        if (!wasWorking) {
            setDoorAnim('opening');
        }
    }, [isWorkingTime]);

    useEffect(() => {
        if (doorAnim !== 'opening') {
            return undefined;
        }
        const id = window.setTimeout(() => {
            setDoorAnim('off');
        }, DOOR_SIGN_OPEN_MS);
        return () => window.clearTimeout(id);
    }, [doorAnim]);

    useEffect(() => {
        setCurrentIndex((i) => Math.min(i, Math.max(0, slideCount - 1)));
    }, [slideCount]);

    useEffect(() => {
        let cancelled = false;
        let page = 0;
        const acc: AnimationScheduleItem[] = [];
        let seededIndex = false;

        (async () => {
            try {
                const fromXlsx = await tryLoadScheduleFromPublicXlsx();
                const fromFile = filterValidScheduleRows(fromXlsx);
                if (!cancelled && fromFile.length > 0) {
                    setScheduleData(dedupeScheduleRows(fromFile));
                    setCurrentIndex(0);
                    setFetchHint(null);
                    return;
                }

                while (!cancelled) {
                    const res = await fetchScheduleAnimationPage({ page, pageSize: DEFAULT_PAGE_SIZE });
                    const valid = filterValidScheduleRows(res.items);
                    acc.push(...valid);
                    const merged = dedupeScheduleRows(acc);

                    if (cancelled) {
                        break;
                    }

                    if (merged.length > 0) {
                        setScheduleData(await attachPublicStaffingRequirements(merged));
                        if (!seededIndex) {
                            setCurrentIndex(0);
                            seededIndex = true;
                        }
                        setFetchHint(null);
                    }

                    if (!res.hasMore) {
                        break;
                    }

                    page += 1;
                }

                if (!cancelled) {
                    const finalRows = dedupeScheduleRows(acc);
                    if (finalRows.length > 0) {
                        setScheduleData(await attachPublicStaffingRequirements(finalRows));
                        setFetchHint(null);
                    } else {
                        setScheduleData([...MOCK_SCHEDULE_ANIMATION_ROWS]);
                        setCurrentIndex(0);
                        setFetchHint(
                            'Показаны демо-данные. Чтобы загрузить реальное расписание, положите schedule.xlsx в artifacts (после run_pipeline) и перезапустите API.',
                        );
                    }
                }
            } catch (err) {
                console.error('schedule fetch', err);
                if (!cancelled) {
                    setScheduleData([...MOCK_SCHEDULE_ANIMATION_ROWS]);
                    setCurrentIndex(0);
                    setFetchHint(
                        'Показаны демо-данные. API недоступен: запустите uvicorn на :8000 и npm run dev (прокси /api).',
                    );
                }
            }
        })();

        return () => {
            cancelled = true;
        };
    }, []);

    const speedFactor = playbackSpeed;

    useEffect(() => {
        if (isPaused || slideCount <= 1) {
            return undefined;
        }

        const hour = currentSlide.hour;
        const isNight = Number.isFinite(hour) && hour >= 0 && hour < WORK_START_HOUR;
        const baseMs = isNight ? OFF_HOURS_SLIDE_MS : WORKING_SLIDE_MS;
        const delayMs = Math.max(40, baseMs / speedFactor);

        const timeoutId = window.setTimeout(() => {
            setCurrentIndex((index) => (index + 1) % slideCount);
        }, delayMs);

        return () => window.clearTimeout(timeoutId);
    }, [isPaused, slideCount, currentIndex, currentSlide.hour, speedFactor]);

    const handleSaveSchedule = () => {
        void fetchPublicScheduleXlsxBlob()
            .then((file) => {
                const fileUrl = URL.createObjectURL(file);
                const link = document.createElement('a');

                link.href = fileUrl;
                link.download = 'schedule.xlsx';
                link.click();
                URL.revokeObjectURL(fileUrl);
            })
            .catch(() => {
                void fetchScheduleExcel()
                    .then((file) => {
                        const fileUrl = URL.createObjectURL(file);
                        const link = document.createElement('a');

                        link.href = fileUrl;
                        link.download = 'schedule.xlsx';
                        link.click();
                        URL.revokeObjectURL(fileUrl);
                    })
                    .catch(() => {});
            });
    };

    const handleSeek = (index: number) => {
        setCurrentIndex(Math.max(0, Math.min(index, slideCount - 1)));
    };

    const handlePrevHour = () => {
        setCurrentIndex((index) => (index - 1 + slideCount) % slideCount);
    };

    const handleNextHour = () => {
        setCurrentIndex((index) => (index + 1) % slideCount);
    };

    const handleSelectDay = useCallback(
        (day: number) => {
            if (day < 1 || day > 7 || !currentSlide) {
                return;
            }
            const idx = findSlideIndexForDay(slides, day, currentSlide.hour);
            setCurrentIndex(idx);
        },
        [slides, currentSlide],
    );

    if (!currentSlide) {
        return null;
    }

    const visitors = visitorsForSlide(currentSlide.items);

    const stationsDimmed = !isWorkingTime || doorAnim === 'opening';
    const showDoorSign = doorAnim === 'closed' || doorAnim === 'opening';

    return (
        <main className="animation">
            <div className="animation__header-band">
                <Header
                    activeDay={currentSlide.day}
                    time={formatHour(currentSlide.hour)}
                    visitorsCount={visitors}
                    onSelectDay={handleSelectDay}
                />
            </div>

            <section
                className={`animation__stations${stationsDimmed ? ' animation__stations--dimmed' : ''}`}
                aria-label="Станции"
            >
                {fetchHint ? (
                    <p className="animation__fetch-hint" role="status">
                        {fetchHint}
                    </p>
                ) : null}
                {showDoorSign ? (
                    <div
                        className={`animation__door-sign${doorAnim === 'opening' ? ' animation__door-sign--opening' : ''}`}
                        aria-hidden
                    >
                        <div className="animation__door-sign-chain" />
                        <div className="animation__door-sign-pivot">
                            <div className="animation__door-sign-card">
                                <div className="animation__door-sign-face animation__door-sign-face--closed">
                                    <span className="animation__door-sign-label">Закрыто</span>
                                    <span className="animation__door-sign-sub">вне рабочих часов</span>
                                </div>
                                <div className="animation__door-sign-face animation__door-sign-face--open">
                                    <span className="animation__door-sign-open-title">Открыто</span>
                                    <div className="animation__door-sign-windows" aria-hidden>
                                        <span className="animation__door-sign-window" />
                                        <span className="animation__door-sign-window" />
                                        <span className="animation__door-sign-window" />
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                ) : null}
                <WeekStationsBoard
                    items={currentSlide.items}
                    previousItems={currentIndex > 0 ? (slides[currentIndex - 1]?.items ?? []) : []}
                />
            </section>

            <div className="animation__footer-band">
                <PlaybackBar
                    currentIndex={currentIndex}
                    slideCount={slideCount}
                    isPaused={isPaused}
                    playbackSpeed={playbackSpeed}
                    onPlaybackSpeedChange={setPlaybackSpeed}
                    onPauseToggle={() => setIsPaused((value) => !value)}
                    onPrevHour={handlePrevHour}
                    onNextHour={handleNextHour}
                    onSeek={handleSeek}
                    onExportSchedule={handleSaveSchedule}
                />
            </div>
        </main>
    );
}

export default Animation;
