"use client";

interface PaginationProps {
  total: number;
  limit: number;
  offset: number;
  onPageChange: (newOffset: number) => void;
}

/**
 * Pagination controls for navigating through paginated data
 */
export function Pagination({ total, limit, offset, onPageChange }: PaginationProps) {
  const safeTotal = total || 0;
  const safeLimit = limit || 20;
  const safeOffset = offset || 0;
  
  const currentPage = Math.floor(safeOffset / safeLimit) + 1;
  const totalPages = Math.ceil(safeTotal / safeLimit);
  const startItem = safeOffset + 1;
  const endItem = Math.min(safeOffset + safeLimit, safeTotal);

  const canGoPrevious = safeOffset > 0;
  const canGoNext = safeOffset + safeLimit < safeTotal;

  const goToPage = (page: number) => {
    const newOffset = (page - 1) * safeLimit;
    onPageChange(newOffset);
  };

  const goPrevious = () => {
    if (canGoPrevious) {
      onPageChange(safeOffset - safeLimit);
    }
  };

  const goNext = () => {
    if (canGoNext) {
      onPageChange(safeOffset + safeLimit);
    }
  };

  // Generate page numbers to show
  const getPageNumbers = (): (number | string)[] => {
    const pages: (number | string)[] = [];
    
    if (totalPages <= 7) {
      // Show all pages
      for (let i = 1; i <= totalPages; i++) {
        pages.push(i);
      }
    } else {
      // Show first, last, current, and neighbors
      if (currentPage <= 3) {
        // Near start
        for (let i = 1; i <= 5; i++) {
          pages.push(i);
        }
        pages.push("...");
        pages.push(totalPages);
      } else if (currentPage >= totalPages - 2) {
        // Near end
        pages.push(1);
        pages.push("...");
        for (let i = totalPages - 4; i <= totalPages; i++) {
          pages.push(i);
        }
      } else {
        // Middle
        pages.push(1);
        pages.push("...");
        for (let i = currentPage - 1; i <= currentPage + 1; i++) {
          pages.push(i);
        }
        pages.push("...");
        pages.push(totalPages);
      }
    }
    
    return pages;
  };

  if (totalPages <= 1) {
    return (
      <div className="pagination">
        <span className="pagination-info">
          Showing {startItem}-{endItem} of {total}
        </span>
      </div>
    );
  }

  return (
    <div className="pagination">
      <span className="pagination-info">
        Showing {startItem}-{endItem} of {total}
      </span>
      
      <div className="pagination-controls">
        <button
          onClick={goPrevious}
          disabled={!canGoPrevious}
          className="pagination-button"
          aria-label="Previous page"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path
              d="M10 12L6 8L10 4"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>

        <div className="pagination-pages">
          {getPageNumbers().map((page, index) => (
            page === "..." ? (
              <span key={`ellipsis-${index}`} className="pagination-ellipsis">...</span>
            ) : (
              <button
                key={page}
                onClick={() => goToPage(page as number)}
                className={`pagination-page ${currentPage === page ? "active" : ""}`}
                aria-label={`Page ${page}`}
                aria-current={currentPage === page ? "page" : undefined}
              >
                {page}
              </button>
            )
          ))}
        </div>

        <button
          onClick={goNext}
          disabled={!canGoNext}
          className="pagination-button"
          aria-label="Next page"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path
              d="M6 12L10 8L6 4"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </div>
    </div>
  );
}
