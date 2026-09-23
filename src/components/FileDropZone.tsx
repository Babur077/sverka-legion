import React, { useRef, useState } from 'react';

interface FileDropZoneProps {
  accept?: string;
  onFile: (file: File) => void | Promise<void>;
  disabled?: boolean;
  className?: string;
  activeClassName?: string;
  rejectedMessage?: string;
  children: React.ReactNode | ((isDragging: boolean) => React.ReactNode);
}

function fileMatchesAccept(file: File, accept?: string): boolean {
  if (!accept?.trim()) return true;

  const rules = accept
    .split(',')
    .map(rule => rule.trim().toLowerCase())
    .filter(Boolean);

  if (!rules.length) return true;

  const fileName = file.name.toLowerCase();
  const mime = file.type.toLowerCase();

  return rules.some(rule => {
    if (rule.startsWith('.')) return fileName.endsWith(rule);
    if (rule.endsWith('/*')) return mime.startsWith(rule.slice(0, -1));
    return mime === rule;
  });
}

export const FileDropZone: React.FC<FileDropZoneProps> = ({
  accept,
  onFile,
  disabled = false,
  className = '',
  activeClassName = 'border-indigo-400 bg-indigo-50 ring-2 ring-indigo-100',
  rejectedMessage = 'Поддерживаются только файлы .xlsx, .xls и .csv.',
  children,
}) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const dragDepthRef = useRef(0);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState('');

  const handleFile = (file: File | null) => {
    if (!file || disabled) return;

    if (!fileMatchesAccept(file, accept)) {
      setError(rejectedMessage);
      return;
    }

    setError('');
    void onFile(file);
  };

  const openPicker = () => {
    if (!disabled) inputRef.current?.click();
  };

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled}
      className={`${className} ${isDragging ? activeClassName : ''} ${disabled ? 'cursor-not-allowed opacity-60' : ''}`.trim()}
      onClick={openPicker}
      onKeyDown={event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          openPicker();
        }
      }}
      onDragEnter={event => {
        event.preventDefault();
        event.stopPropagation();
        if (disabled) return;
        dragDepthRef.current += 1;
        setIsDragging(true);
      }}
      onDragOver={event => {
        event.preventDefault();
        event.stopPropagation();
        if (!disabled) event.dataTransfer.dropEffect = 'copy';
      }}
      onDragLeave={event => {
        event.preventDefault();
        event.stopPropagation();
        if (disabled) return;
        dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
        if (dragDepthRef.current === 0) setIsDragging(false);
      }}
      onDrop={event => {
        event.preventDefault();
        event.stopPropagation();
        dragDepthRef.current = 0;
        setIsDragging(false);
        handleFile(event.dataTransfer.files?.[0] || null);
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        disabled={disabled}
        onChange={event => {
          handleFile(event.target.files?.[0] || null);
          event.currentTarget.value = '';
        }}
      />

      {typeof children === 'function' ? children(isDragging) : children}

      {error && (
        <div className="mt-2 text-[11px] font-semibold text-rose-600">
          {error}
        </div>
      )}
    </div>
  );
};
