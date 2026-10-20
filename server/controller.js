const axios = require('axios')
const dotenv = require('dotenv')

dotenv.config()

// APOD Basic JSON feed from science.nasa.gov; it replaced the unreliable api.nasa.gov APOD API
// https://api.nasa.gov/assets/files/apod/APOD-APIs-and-RSS-info.pdf
const nasaApiUrl = process.env.NASA_API_URL || 'https://science.nasa.gov/wp-json/wp/v2/apod-basic'

// Retry transient 5xx and network errors with backoff
const MAX_ATTEMPTS = 3
const RETRY_BASE_DELAY_MS = 200
const REQUEST_TIMEOUT_MS = 5000

// Last good image per date, served when NASA is down
const MAX_CACHE_ENTRIES = 100
const lastGoodImages = new Map()

/** Image Collection Transactions */

const getImage = async(req, response) => {
  console.log('**** GETTING IMAGE ****')

  const requestedDate = req.query.date;

  if (requestedDate && !isValidApodDate(requestedDate)) {
    return response.status(400).json({
      success: false,
      error: 'Date must be between 1995-06-16 and today'
    });
  }

  const cacheKey = requestedDate || 'today';

  try {
    // A single day is /{YYMMDD}; the newest-first list stands in for "today"
    const res = requestedDate
      ? await fetchWithRetry(`${nasaApiUrl}/${toLegacyDateCode(requestedDate)}`)
      : await fetchWithRetry(nasaApiUrl, { per_page: 1 });
    const apod = Array.isArray(res.data) ? res.data[0] : res.data;

    if (!apod) {
      throw new Error('APOD feed returned no posts');
    }

    const nasaImage = toNasaImage(apod);

    rememberImage(cacheKey, nasaImage);

    return response.status(200).json({
      success: true,
      item: nasaImage
    });
  } catch (error) {
    console.error(`Unable to fetch the NASA image: ${error.message}`)

    if (error.response && error.response.status === 404) {
      return response.status(404).json({
        success: false,
        error: 'No APOD was published for that date'
      });
    }

    const cachedImage = lastGoodImages.get(cacheKey);
    if (cachedImage) {
      console.log(`Serving cached NASA image for ${cacheKey}`)
      return response.status(200).json({
        success: true,
        stale: true,
        item: cachedImage
      });
    }

    return response.status(502).json({
      success: false,
      error: 'Unable to fetch the NASA image'
    });
  }
}

// The feed returns HTML in text fields and hides video embeds inside basic_html,
// so normalize it to the shape the frontend expects
function toNasaImage(apod) {
  const embedUrl = findEmbedUrl(apod.basic_html);
  const isVideo = apod.media_type !== 'image' && Boolean(embedUrl);
  const imageUrl = apod.hdurl || null;

  return {
    title: htmlToText(apod.title),
    date: apod.date,
    // Drop the label and the site's trailing navigation, which the old API didn't include
    explanation: htmlToText(apod.explanation)
      .replace(/^Explanation:\s*/i, '')
      .replace(/\s*(?:Tomorrow's picture:|Explore Your Universe:).*$/is, ''),
    attribution: htmlToText(apod.copyright || apod.credit)
      .replace(/^[^:]*\b(?:credit|copyright)\b[^:]*:\s*/i, '') || 'NASA',
    mediaType: isVideo ? 'video' : 'image',
    mediaUrl: isVideo ? embedUrl : imageUrl,
    imageUrl,
    hdImageUrl: imageUrl
  };
}

function findEmbedUrl(html) {
  const match = /<iframe[^>]*\ssrc="([^"]+)"/i.exec(html || '');
  if (!match) {
    return null;
  }
  const src = decodeEntities(match[1]);
  return src.startsWith('//') ? `https:${src}` : src;
}

function htmlToText(html) {
  // Line and paragraph breaks become spaces; inline tags are dropped so words stay intact
  return decodeEntities(String(html || '').replace(/<(?:br|\/?p)\b[^>]*>/gi, ' ').replace(/<[^>]*>/g, ''))
    .replace(/\s+/g, ' ')
    .replace(/\s+([,.;:!?)]|'s\b)/g, '$1')
    .replace(/\(\s+/g, '(')
    .trim();
}

const NAMED_ENTITIES = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' };

function decodeEntities(text) {
  return text.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (entity, code) => {
    if (code[0] === '#') {
      const point = code[1].toLowerCase() === 'x' ? parseInt(code.slice(2), 16) : parseInt(code.slice(1), 10);
      return point <= 0x10ffff ? String.fromCodePoint(point) : entity;
    }
    return NAMED_ENTITIES[code.toLowerCase()] ?? entity;
  });
}

// 2024-01-05 -> 240105, the feed's legacy APOD date code
function toLegacyDateCode(date) {
  return date.slice(2).replace(/-/g, '');
}

async function fetchWithRetry(url, params) {
  for (let attempt = 1; ; attempt++) {
    try {
      return await axios.get(url, { params, timeout: REQUEST_TIMEOUT_MS });
    } catch (error) {
      if (attempt >= MAX_ATTEMPTS || !isRetryable(error)) {
        throw error;
      }
      const delay = RETRY_BASE_DELAY_MS * 2 ** (attempt - 1);
      console.warn(`NASA request failed (${error.message}), retrying in ${delay}ms`)
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
}

// Retry network errors, timeouts and 5xx; client errors won't succeed on retry
function isRetryable(error) {
  return !error.response || error.response.status >= 500;
}

function rememberImage(key, image) {
  lastGoodImages.delete(key);
  lastGoodImages.set(key, image);
  if (lastGoodImages.size > MAX_CACHE_ENTRIES) {
    lastGoodImages.delete(lastGoodImages.keys().next().value);
  }
}

function isValidApodDate(date) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return false;
  }

  const parsedDate = new Date(`${date}T00:00:00Z`);
  const today = new Date().toISOString().slice(0, 10);

  return !Number.isNaN(parsedDate.getTime()) &&
    parsedDate.toISOString().slice(0, 10) === date &&
    date >= '1995-06-16' &&
    date <= today;
}
module.exports = {
  getImage
}
