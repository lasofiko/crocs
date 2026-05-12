/** Чёрная силуэтная иконка «картофель фри». */
export function FriesIconBlack({ className = '' }: { className?: string }) {
    return (
        <svg
            className={className}
            width={22}
            height={22}
            viewBox="0 0 24 24"
            aria-hidden
            focusable="false"
        >
            <g fill="#121212">
                <rect x="6" y="5" width="2.4" height="14" rx="1.1" transform="rotate(-10 7.2 12)" />
                <rect x="9" y="3" width="2.4" height="16" rx="1.1" />
                <rect x="12" y="4" width="2.4" height="15" rx="1.1" transform="rotate(6 13.2 11.5)" />
                <rect x="15" y="5" width="2.4" height="14" rx="1.1" transform="rotate(14 16.2 12)" />
                <rect x="4.5" y="8" width="2.2" height="11" rx="1" transform="rotate(-18 5.6 13.5)" />
            </g>
            <ellipse cx="12" cy="18.5" rx="8.5" ry="2.3" fill="#121212" />
        </svg>
    );
}
