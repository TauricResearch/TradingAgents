// Last module patch version validated against: 3.0.1

export interface RandomNumberGenerationSource {
    /**
     * Returns the same type of function for generating random numbers but where the given random number
     * generator source is used as the source of randomness instead of Math.random.
     * This is useful when a seeded random number generator is preferable to Math.random.
     *
     * @param source Source (pseudo-)random number generator implementing the Math.random interface.
     * The given random number generator must implement the same interface as Math.random and
     * only return values in the range [0, 1).
     */
    source(source: () => number): this;
}

/**
 * A configurable random number generator for the uniform distribution.
 */
export interface RandomUniform extends RandomNumberGenerationSource {
    /**
     * Returns a function for generating random numbers with a uniform distribution.
     * The minimum allowed value of a returned number is min (inclusive), and the maximum is max (exclusive).
     * Min defaults to 0; if max is not specified, it defaults to 1.
     *
     * @param max The maximum allowed value of a returned number, defaults to 1.
     */
    (max?: number): () => number;
    /**
     * Returns a function for generating random numbers with a uniform distribution.
     * The minimum allowed value of a returned number is min (inclusive), and the maximum is max (exclusive).
     *
     * @param min The minimum allowed value of a returned number.
     * @param max The maximum allowed value of a returned number.
     */
    // tslint:disable-next-line:unified-signatures
    (min: number, max: number): () => number;
}

export const randomUniform: RandomUniform;

/**
 * A configurable random integer generator for the uniform distribution.
 */
export interface RandomInt extends RandomNumberGenerationSource {
    /**
     * Returns a function for generating random integers with a uniform distribution.
     * The minimum allowed value of a returned number is ⌊min⌋ (inclusive), and the maximum is ⌊max - 1⌋ (inclusive)
     * Min defaults to 0.
     *
     * @param max The maximum allowed value of a returned number.
     */
    (max: number): () => number;
    /**
     * Returns a function for generating random integers with a uniform distribution.
     * The minimum allowed value of a returned number is ⌊min⌋ (inclusive), and the maximum is ⌊max - 1⌋ (inclusive)
     *
     * @param min The minimum allowed value of a returned number.
     * @param max The maximum allowed value of a returned number.
     */
    // tslint:disable-next-line:unified-signatures
    (min: number, max: number): () => number;
}

export const randomInt: RandomInt;

/**
 * A configurable random number generator for the normal (Gaussian) distribution.
 */
export interface RandomNormal extends RandomNumberGenerationSource {
    /**
     * Returns a function for generating random numbers with a normal (Gaussian) distribution.
     * The expected value of the generated numbers is mu, with the given standard deviation sigma.
     * If mu is not specified, it defaults to 0; if sigma is not specified, it defaults to 1.
     *
     * @param mu Expected value, defaults to 0.
     * @param sigma Standard deviation, defaults to 1.
     */
    (mu?: number, sigma?: number): () => number;
}

export const randomNormal: RandomNormal;

/**
 * A configurable random number generator for the log-normal distribution.
 */
export interface RandomLogNormal extends RandomNumberGenerationSource {
    /**
     * Returns a function for generating random numbers with a log-normal distribution. The expected value of the random variable’s natural logarithm is mu,
     * with the given standard deviation sigma. If mu is not specified, it defaults to 0; if sigma is not specified, it defaults to 1.
     *
     * @param mu Expected value, defaults to 0.
     * @param sigma Standard deviation, defaults to 1.
     */
    (mu?: number, sigma?: number): () => number;
}

export const randomLogNormal: RandomLogNormal;

/**
 * A configurable random number generator for the Bates distribution.
 */
export interface RandomBates extends RandomNumberGenerationSource {
    /**
     * Returns a function for generating random numbers with a Bates distribution with n independent variables.
     * The case of fractional n is handled as with d3.randomIrwinHall, and d3.randomBates(0) is equivalent to d3.randomUniform().
     *
     * @param n Number of independent random variables to use.
     */
    (n: number): () => number;
}

export const randomBates: RandomBates;

/**
 * A configurable random number generator for the Irwin–Hall distribution.
 */
export interface RandomIrwinHall extends RandomNumberGenerationSource {
    /**
     * Returns a function for generating random numbers with an Irwin–Hall distribution with n independent variables.
     * If the fractional part of n is non-zero, this is treated as adding d3.randomUniform() times that fractional part to the integral part.
     *
     * @param n Number of independent random variables to use.
     */
    (n: number): () => number;
}

export const randomIrwinHall: RandomIrwinHall;

/**
 * A configurable random number generator for the exponential distribution.
 */
export interface RandomExponential extends RandomNumberGenerationSource {
    /**
     * Returns a function for generating random numbers with an exponential distribution with the rate lambda;
     * equivalent to time between events in a Poisson process with a mean of 1 / lambda.
     *
     * @param lambda Expected time between events.
     */
    (lambda: number): () => number;
}

export const randomExponential: RandomExponential;

/**
 * A configurable random number generator with an Pareto distribution.
 */
export interface RandomPareto extends RandomNumberGenerationSource {
    /**
     * Returns a function for generating random numbers with a Pareto distribution with the shape alpha.
     * The value alpha must be a positive value.
     *
     * @param alpha alpha
     */
    (alpha: number): () => number;
}

export const randomPareto: RandomPareto;

/**
 * A configurable random 0 or 1 generator according to a Bernoulli distribution.
 */
export interface RandomBernoulli extends RandomNumberGenerationSource {
    /**
     * Returns a function for generating either 1 or 0 according to a Bernoulli distribution with 1 being returned with success probability p and 0 with failure probability q = 1 - p.
     * The value p is in the range [0, 1].
     *
     * @param p p
     */
    (p: number): () => number;
}

export const randomBernoulli: RandomBernoulli;

/**
 * A configurable random number generator with a geometric distribution.
 */
export interface RandomGeometric extends RandomNumberGenerationSource {
    /**
     * Returns a function for generating numbers with a geometric distribution with success probability p.
     * The value p is in the range [0, 1].
     *
     * @param p Success probability
     */
    (p: number): () => number;
}

export const randomGeometric: RandomGeometric;

/**
 * A configurable random number generator with a binomial distribution.
 */
export interface RandomBinomial extends RandomNumberGenerationSource {
    /**
     * Returns a function for generating numbers with a geometric distribution with success probability p.
     * The value p is in the range (0, 1].
     *
     * @param p Success probability
     */
    (p: number): () => number;
}

export const randomBinomial: RandomBinomial;

/**
 * A configurable random number generator with a gamma distribution.
 */
export interface RandomGamma extends RandomNumberGenerationSource {
    /**
     * Returns a function for generating random numbers with a gamma distribution with k the shape parameter and theta the scale parameter.
     * The value k must be a positive value; if theta is not specified, it defaults to 1.
     *
     * @param k Shape parameter
     * @param theta Scale paramter
     */
    (k: number, theta?: number): () => number;
}

export const randomGamma: RandomGamma;

/**
 * A configurable random number generator with a beta distribution.
 */
export interface RandomBeta extends RandomNumberGenerationSource {
    /**
     * Returns a function for generating random numbers with a beta distribution with alpha and beta shape parameters, which must both be positive.
     *
     * @param alpha Shape parameter
     * @param beta Shape paramter
     */
    (alpha: number, beta: number): () => number;
}

export const randomBeta: RandomBeta;

/**
 * A configurable random number generator with one of the generalized extreme value distributions.
 */
export interface RandomWeibull extends RandomNumberGenerationSource {
    /**
     * Returns a function for generating random numbers with one of the generalized extreme value distributions, depending on k:
     * If k is positive, the Weibull distribution with shape parameter k
     * If k is zero, the Gumbel distribution
     * If k is negative, the Fréchet distribution with shape parameter −k
     * In all three cases, a is the location parameter and b is the scale parameter.
     * If a is not specified, it defaults to 0; if b is not specified, it defaults to 1.
     *
     * @param k Shape parameter
     * @param a Location parameter
     * @param b Scale parameter
     */
    (k: number, a?: number, b?: number): () => number;
}

export const randomWeibull: RandomWeibull;

/**
 * A configurable random number generator with a Cauchy distribution.
 */
export interface RandomCauchy extends RandomNumberGenerationSource {
    /**
     * Returns a function for generating random numbers with a Cauchy distribution.
     * a and b have the same meanings and default values as in d3.randomWeibull.
     *
     * @param a Location parameter
     * @param b Scale parameter
     */
    (a?: number, b?: number): () => number;
}

export const randomCauchy: RandomCauchy;

/**
 * A configurable random number generator with a logistic distribution.
 */
export interface RandomLogistic extends RandomNumberGenerationSource {
    /**
     * Returns a function for generating random numbers with a logistic distribution.
     * a and b have the same meanings and default values as in d3.randomWeibull.
     *
     * @param a Location parameter
     * @param b Scale parameter
     */
    (a?: number, b?: number): () => number;
}

export const randomLogistic: RandomLogistic;

/**
 * A configurable random number generator with a Poisson distribution.
 */
export interface RandomPoisson extends RandomNumberGenerationSource {
    /**
     * Returns a function for generating random numbers with a Poisson distribution with mean lambda.
     *
     * @param lambda Mean
     */
    (lambda: number): () => number;
}

export const randomPoisson: RandomPoisson;

/**
 * Returns a linear congruential generator;
 * this function can be called repeatedly to obtain pseudorandom values well-distributed on the interval [0,1) and with a long period (up to 1 billion numbers), similar to Math.random.
 * A seed can be specified as a real number in the interval [0,1) or as any integer.
 * In the latter case, only the lower 32 bits are considered.
 * Two generators instanced with the same seed generate the same sequence, allowing to create reproducible pseudo-random experiments.
 * If the seed is not specified, one is chosen using Math.random.
 *
 * @param seed A seed that is either a real number in the interval [0,1) or any integer.
 */
export function randomLcg(seed?: number): () => number;
