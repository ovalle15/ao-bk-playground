const axios = require('axios')
const dotenv = require('dotenv')

dotenv.config()

const nasaApiUrl = process.env.NASA_API_URL || 'https://api.nasa.gov/planetary/apod'

// NASA's APOD API intermittently returns 5xx, so retry those with backoff
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
    const res = await fetchWithRetry({
      api_key: process.env.API_TOKEN,
      thumbs: true,
      ...(requestedDate && { date: requestedDate })
    });
    const nasaImage = {
      title: res.data.title,
      date: res.data.date,
      explanation: res.data.explanation,
      attribution: res.data.copyright || 'NASA',
      mediaType: res.data.media_type,
      mediaUrl: res.data.url,
      imageUrl: res.data.thumbnail_url || res.data.url,
      hdImageUrl: res.data.hdurl || res.data.url
    };

    rememberImage(cacheKey, nasaImage);

    return response.status(200).json({
      success: true,
      item: nasaImage
    });
  } catch (error) {
    console.error(`Unable to fetch the NASA image: ${error.message}`)

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

async function fetchWithRetry(params) {
  for (let attempt = 1; ; attempt++) {
    try {
      return await axios.get(nasaApiUrl, { params, timeout: REQUEST_TIMEOUT_MS });
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
